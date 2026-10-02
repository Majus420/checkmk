#!/usr/bin/env python3
# Author: Marius Gielnik
# License: GNU General Public License v2 or later
"""Check plug-in: Docker container CPU utilization, normalized to the available CPUs."""

import time
from dataclasses import dataclass
from typing import Any, Mapping

from cmk.agent_based.v2 import (
    AgentSection,
    check_levels,
    CheckPlugin,
    CheckResult,
    DiscoveryResult,
    IgnoreResultsError,
    Metric,
    render,
    Result,
    Service,
    State,
    StringTable,
    get_value_store,
)


@dataclass(frozen=True)
class Section:
    raw_percent: float  # 100 % = one fully used CPU core (Linux 'docker stats' style)
    host_cpus: int
    limit_cpus: float  # 0 = container has no CPU limit


def parse_docker_cpu_normalized(string_table: StringTable) -> Section | None:
    for line in string_table:
        if len(line) < 3:
            continue
        try:
            raw, host, limit = float(line[0]), int(float(line[1])), float(line[2])
        except ValueError:
            return None
        if host <= 0:
            return None
        return Section(raw_percent=raw, host_cpus=host, limit_cpus=limit)
    return None


agent_section_docker_cpu_normalized = AgentSection(
    name="docker_cpu_normalized",
    parse_function=parse_docker_cpu_normalized,
)


_MAX_GAP = 1800  # seconds without data after which a running "above threshold" period is reset


def _check_levels_over_time(
    util: float, levels: Mapping[str, float], value_store: dict[str, Any], now: float
) -> CheckResult:
    """Alarm only if util stays at or above a threshold for a given time.

    The duration is measured with the wall clock of the check, never with the
    Docker tick counters (those are nanoseconds, see Werk 20187).
    """
    threshold = levels["threshold"]
    last_seen = value_store.get("last_seen")
    value_store["last_seen"] = now
    if util < threshold:
        value_store.pop("above_since", None)
        return
    since = value_store.get("above_since")
    if since is None or since > now or (last_seen is not None and now - last_seen > _MAX_GAP):
        since = now
    value_store["above_since"] = since
    yield from check_levels(
        now - since,
        levels_upper=("fixed", (levels["warn_after"], levels["crit_after"])),
        render_func=render.timespan,
        label=f"Total CPU at or above {render.percent(threshold)} for",
    )


def _check_docker_cpu_normalized(
    params: Mapping[str, Any], section: Section, value_store: dict[str, Any], now: float
) -> CheckResult:
    # A CPU limit only counts if it is smaller than the host (a bigger value is meaningless).
    if 0 < section.limit_cpus <= section.host_cpus:
        effective_cpus = section.limit_cpus
        basis = "container CPU limit"
    else:
        effective_cpus = float(section.host_cpus)
        basis = "host CPUs"

    cores_used = section.raw_percent / 100.0
    util = section.raw_percent / effective_cpus
    yield from check_levels(
        util,
        levels_upper=params["util"],
        metric_name="util",
        render_func=render.percent,
        label="Total CPU",
        boundaries=(0, 100),
    )
    mode, levels = params["levels_over_time"]
    if mode == "levels":
        yield from _check_levels_over_time(util, levels, value_store, now)
    else:
        value_store.pop("above_since", None)
    yield Result(
        state=State.OK,
        summary=f"{cores_used:.2f} of {effective_cpus:g} CPUs in use ({basis})",
    )
    yield Metric("docker_cpu_cores_used", cores_used)


def _section_from_builtin(
    builtin: Any, value_store: dict[str, Any], now: float
) -> Section | CheckResult:
    """Normalize the standard Docker data (section cpu_utilization_os).

    The standard Docker check reports "CPU cores in use x 100 %". This function
    turns the same counters into a Section so that the common check logic can
    divide by the number of CPUs. Repeated data (the agent plug-in of Docker only
    refreshes every few minutes) does not raise an error, the last value is reused.
    """
    time_base = float(builtin.time_base)
    time_cpu = float(builtin.time_cpu)
    num_cpus = int(builtin.num_cpus)
    if num_cpus <= 0:
        raise IgnoreResultsError("Number of CPUs is not available")

    last = value_store.get("builtin_last")
    if last is None or time_base < last["time_base"] or time_cpu < last["time_cpu"]:
        # first run, or the counters were reset (container restart)
        value_store["builtin_last"] = {
            "time_base": time_base,
            "time_cpu": time_cpu,
            "cores": None,
            "changed": now,
        }
        raise IgnoreResultsError("Initialized, result available with the next new data")

    if time_base > last["time_base"]:
        cores = (time_cpu - last["time_cpu"]) / (time_base - last["time_base"])
        value_store["builtin_last"] = {
            "time_base": time_base,
            "time_cpu": time_cpu,
            "cores": cores,
            "changed": now,
        }
    else:
        cores = last["cores"]
        if cores is None:
            raise IgnoreResultsError("Waiting for new data")
        if now - last["changed"] > _MAX_GAP:
            return _stale_result(now - last["changed"])

    return Section(raw_percent=cores * 100.0, host_cpus=num_cpus, limit_cpus=0.0)


def _stale_result(age: float) -> CheckResult:
    yield Result(
        state=State.UNKNOWN,
        summary=f"No new CPU data for {render.timespan(age)}",
    )


def discover_docker_cpu_normalized(
    params: Mapping[str, Any],
    section_docker_cpu_normalized: Section | None,
    section_docker_container_status: Any | None,
    section_cpu_utilization_os: Any | None,
) -> DiscoveryResult:
    if section_docker_cpu_normalized is not None:
        yield Service()
    elif (
        params["create_from_builtin"]
        and section_docker_container_status is not None
        and section_cpu_utilization_os is not None
    ):
        yield Service()


def check_docker_cpu_normalized(
    params: Mapping[str, Any],
    section_docker_cpu_normalized: Section | None,
    section_docker_container_status: Any | None,
    section_cpu_utilization_os: Any | None,
) -> CheckResult:
    yield from _check(
        params,
        section_docker_cpu_normalized,
        section_cpu_utilization_os,
        get_value_store(),
        time.time(),
    )


def _check(
    params: Mapping[str, Any],
    own: Section | None,
    builtin: Any | None,
    value_store: dict[str, Any],
    now: float,
) -> CheckResult:
    if own is not None:
        yield from _check_docker_cpu_normalized(params, own, value_store, now)
        return
    if builtin is None:
        return
    section = _section_from_builtin(builtin, value_store, now)
    if isinstance(section, Section):
        yield from _check_docker_cpu_normalized(params, section, value_store, now)
    else:
        yield from section


check_plugin_docker_cpu_normalized = CheckPlugin(
    name="docker_cpu_normalized",
    service_name="Docker CPU utilization",
    sections=["docker_cpu_normalized", "docker_container_status", "cpu_utilization_os"],
    discovery_function=discover_docker_cpu_normalized,
    discovery_default_parameters={"create_from_builtin": False},
    discovery_ruleset_name="docker_cpu_normalized_discovery",
    check_function=check_docker_cpu_normalized,
    check_default_parameters={
        "util": ("no_levels", None),
        "levels_over_time": (
            "levels",
            {"threshold": 90.0, "warn_after": 5400.0, "crit_after": 10800.0},
        ),
    },
    check_ruleset_name="docker_cpu_normalized",
)
