#!/usr/bin/env python3
"""
win_smb_shares - section parser and check plug-in: Windows SMB share performance

Author:   Marius Gielnik
Project:  https://github.com/Majus420/checkmk/tree/main/MKP/windows_smb_share_performance
License:  GPL-2.0-or-later

Section:  <<<win_smb_shares:sep(9)>>> from the agent plug-in win_smb_shares.ps1
          (raw counters of "SMB Server Shares" plus their CounterType, read via
          .NET performance counters, WMI only as reported fallback).
Service:  "SMB Share <name>" per share. Discovery filter: rule
          "Windows SMB share discovery" (default: no administrative shares
          C$/D$/..., ADMIN$, IPC$, print$ and no _Total; hidden user shares
          like home$ are discovered).
Paths:    the local path of every share (Win32_Share) is shown in the service
          details. The discovery rule accepts plain local paths (E:\\home,
          D:\\Shares\\Public, E:\\* for everything below E:) instead of share names.
Values:   latency per data/read/write/any request, average data/read/write
          queue length, current data queue length, pending requests,
          data/read/write/metadata requests per second, throughput,
          open files and connections. No request in an interval is shown as
          "no requests" instead of a latency of 0.
          Rates are computed from two consecutive agent outputs according to
          the CounterType reported by Windows, so changed counter definitions
          on other Windows versions are handled instead of guessed.
Levels:   rule "Windows SMB share performance". Defaults: data/read/write latency
          20/50 ms, avg. and current data queue length 2/5. 20 ms and queue 2
          are Microsoft's rules of thumb for the matching disk counters, the CRIT
          values are the author's choice. "No levels" in a rule switches a default off.
"""

from __future__ import annotations

import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from cmk.agent_based.v2 import (
    AgentSection,
    CheckPlugin,
    CheckResult,
    DiscoveryResult,
    Result,
    RuleSetType,
    Service,
    State,
    StringTable,
    check_levels,
    get_value_store,
    render,
)

# Windows performance counter types (winperf.h)
_RAW_TYPES = {65536, 65792}  # PERF_COUNTER_RAWCOUNT, PERF_COUNTER_LARGE_RAWCOUNT
_AVERAGE_TIMER = 805438464  # PERF_AVERAGE_TIMER (needs <name>_Base)
_QUEUELEN_PERFTIME = {4523008, 4523264}  # PERF_COUNTER_(LARGE_)QUEUELEN_TYPE
_QUEUELEN_100NS = 5571840  # PERF_COUNTER_100NS_QUEUELEN_TYPE
_RATE_PERFTIME = {272696320, 272696576}  # PERF_COUNTER_COUNTER, PERF_COUNTER_BULK_COUNT

_SHARE_PREFIX = re.compile(r"^\\\\[^\\]*\\")

# (counter property, parameter key, metric name, label, render, shown in summary)
_VALUES: tuple[tuple[str, str, str, str, Any, bool], ...] = (
    ("AvgsecPerDataRequest", "latency_data", "win_smb_share_latency_data", "Data latency", render.timespan, True),
    ("AvgsecPerRead", "latency_read", "win_smb_share_latency_read", "Read latency", render.timespan, True),
    ("AvgsecPerWrite", "latency_write", "win_smb_share_latency_write", "Write latency", render.timespan, True),
    ("AvgsecPerRequest", "latency_request", "win_smb_share_latency_request", "Request latency (all requests)", render.timespan, False),
    ("AvgDataQueueLength", "queue_avg_data", "win_smb_share_queue_avg_data", "Avg. data queue length", lambda v: f"{v:.2f}", True),
    ("AvgReadQueueLength", "queue_avg_read", "win_smb_share_queue_avg_read", "Avg. read queue length", lambda v: f"{v:.2f}", False),
    ("AvgWriteQueueLength", "queue_avg_write", "win_smb_share_queue_avg_write", "Avg. write queue length", lambda v: f"{v:.2f}", False),
    ("CurrentDataQueueLength", "queue_current_data", "win_smb_share_queue_current_data", "Current data queue length", lambda v: f"{v:.0f}", True),
    ("CurrentPendingRequests", "pending_requests", "win_smb_share_pending_requests", "Pending requests", lambda v: f"{v:.0f}", False),
    ("DataRequestsPersec", "requests_data", "win_smb_share_requests_data", "Data requests", lambda v: f"{v:.1f}/s", True),
    ("ReadRequestsPersec", "requests_read", "win_smb_share_requests_read", "Read requests", lambda v: f"{v:.1f}/s", False),
    ("WriteRequestsPersec", "requests_write", "win_smb_share_requests_write", "Write requests", lambda v: f"{v:.1f}/s", False),
    ("MetadataRequestsPersec", "requests_metadata", "win_smb_share_requests_metadata", "Metadata requests", lambda v: f"{v:.1f}/s", False),
    ("DataBytesPersec", "throughput_data", "win_smb_share_throughput_data", "Throughput", render.iobandwidth, True),
    ("ReadBytesPersec", "throughput_read", "win_smb_share_throughput_read", "Read throughput", render.iobandwidth, False),
    ("WriteBytesPersec", "throughput_write", "win_smb_share_throughput_write", "Write throughput", render.iobandwidth, False),
    ("CurrentOpenFileCount", "open_files", "win_smb_share_open_files", "Open files", lambda v: f"{v:.0f}", True),
    ("TreeConnectCount", "tree_connects", "win_smb_share_tree_connects", "Connections", lambda v: f"{v:.0f}", False),
)

# default: only the administrative shares Windows creates itself, hidden user shares (name$) stay in
# default levels: 20 ms latency / current queue 2 follow Microsoft's rules of thumb for the
# disk counters the SMB share counters were modelled after; the CRIT values are the author's choice
CHECK_DEFAULT: dict[str, Any] = {
    "latency_data": ("fixed", (0.02, 0.05)),
    "latency_read": ("fixed", (0.02, 0.05)),
    "latency_write": ("fixed", (0.02, 0.05)),
    "queue_avg_data": ("fixed", (2.0, 5.0)),
    "queue_current_data": ("fixed", (2.0, 5.0)),
}

DISCOVERY_DEFAULT: dict[str, Any] = {
    "exclude": [r"^[A-Za-z]\$$", r"^(ADMIN|IPC|print)\$$", r"^_Total$"]
}


@dataclass
class SmbSection:
    types: dict[str, int] = field(default_factory=dict)
    shares: dict[str, dict[str, int]] = field(default_factory=dict)
    paths: dict[str, str] = field(default_factory=dict)
    source: str = ""
    error: str | None = None


def _to_int(text: str) -> int | None:
    try:
        return int(text.strip())
    except ValueError:
        return None


def _key_values(fields: list[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in fields:
        key, sep, raw = item.partition("=")
        if not sep:
            continue
        value = _to_int(raw)
        if value is not None:
            result[key.strip()] = value
    return result


def share_name(raw_name: str) -> str:
    """'\\\\*\\home' or '\\\\SERVER\\home' -> 'home'; '_Total' stays as is."""
    return _SHARE_PREFIX.sub("", raw_name.strip()) or raw_name.strip()


def parse_win_smb_shares(string_table: StringTable) -> SmbSection:
    section = SmbSection()
    for line in string_table:
        if not line or not line[0].strip():
            continue
        head = line[0].strip()
        if head == "[types]":
            section.types.update(_key_values(line[1:]))
        elif head == "[source]":
            section.source = line[1].strip() if len(line) > 1 else ""
        elif head == "[share]":
            if len(line) > 2 and line[1].strip():
                section.paths[line[1].strip()] = line[2].strip()
        elif head == "[error]":
            section.error = " ".join(f.strip() for f in line[1:]).strip() or "unknown error"
        else:
            section.shares[share_name(head)] = _key_values(line[1:])
    return section


agent_section_win_smb_shares = AgentSection(
    name="win_smb_shares",
    parse_function=parse_win_smb_shares,
)


def _matches(patterns: object, text: str, flags: int = 0) -> bool:
    if not isinstance(patterns, (list, tuple)):
        return False
    for pattern in patterns:
        try:
            if re.search(str(pattern), text, flags):
                return True
        except re.error:
            continue
    return False


def normalize_path(path: str) -> str:
    """Case insensitive, / or \\, no trailing backslash: 'e:/Home\\' -> 'e:\\home'."""
    norm = path.strip().strip('"').replace("/", "\\").lower()
    while len(norm) > 2 and norm.endswith("\\"):
        norm = norm[:-1]
    return norm


def path_selected(share_path: str, wanted: object) -> bool:
    """True if the share path equals one of the entered paths; 'X:\\dir\\*' selects everything below dir."""
    if not share_path or not isinstance(wanted, (list, tuple)):
        return False
    have = normalize_path(share_path)
    for entry in wanted:
        text = str(entry).strip()
        if not text:
            continue
        if text.endswith("*"):
            base = normalize_path(text[:-1])
            if have == base or have.startswith(base.rstrip("\\") + "\\"):
                return True
        elif have == normalize_path(text):
            return True
    return False


def discover_win_smb_shares(params: Mapping[str, Any], section: SmbSection) -> DiscoveryResult:
    include = params.get("include")
    exclude = params.get("exclude", DISCOVERY_DEFAULT["exclude"])
    paths = params.get("paths")
    for name in sorted(section.shares):
        if include and not _matches(include, name):
            continue
        if _matches(exclude, name):
            continue
        if paths and not path_selected(section.paths.get(name, ""), paths):
            continue
        yield Service(item=name)


def _delta(cur: Mapping[str, int], prev: Mapping[str, int], key: str) -> int | None:
    if key not in cur or key not in prev:
        return None
    return cur[key] - prev[key]


class _CounterReset(Exception):
    pass


class _NoRequests(Exception):
    """Average timer without any request in the interval: there is no latency, not a latency of 0."""


def compute_value(
    prop: str, types: Mapping[str, int], cur: Mapping[str, int], prev: Mapping[str, int] | None
) -> float | None:
    """Value of one counter according to its Windows CounterType, None if not computable yet."""
    ctype = types.get(prop)
    if ctype is None or prop not in cur:
        return None
    if ctype in _RAW_TYPES:
        return float(cur[prop])
    if prev is None:
        return None
    dx = _delta(cur, prev, prop)
    if dx is None:
        return None
    if dx < 0:
        raise _CounterReset()

    if ctype == _AVERAGE_TIMER:
        dbase = _delta(cur, prev, f"{prop}_Base")
        freq = cur.get("Frequency_PerfTime")
        if dbase is None or not freq:
            return None
        if dbase < 0:
            raise _CounterReset()
        if dbase == 0:
            raise _NoRequests()
        return dx / freq / dbase

    if ctype in _QUEUELEN_PERFTIME or ctype == _QUEUELEN_100NS:
        clock = "Timestamp_Sys100NS" if ctype == _QUEUELEN_100NS else "Timestamp_PerfTime"
        dt = _delta(cur, prev, clock)
        if dt is None or dt <= 0:
            return None
        return dx / dt

    if ctype in _RATE_PERFTIME:
        dt = _delta(cur, prev, "Timestamp_PerfTime")
        freq = cur.get("Frequency_PerfTime")
        if dt is None or dt <= 0 or not freq:
            return None
        return dx / (dt / freq)

    return None  # unknown counter type: never guess


def _timestamp(sample: Mapping[str, int]) -> int | None:
    return sample.get("Timestamp_Sys100NS", sample.get("Timestamp_PerfTime"))


def compute_values(
    types: Mapping[str, int], cur: Mapping[str, int], store: dict[str, Any]
) -> tuple[dict[str, float], list[str]]:
    """Computes all values; keeps the last sample and results in the value store.

    Identical samples (cached plug-in output) reuse the last results, counter
    resets or a clock running backwards start over from the new sample.
    """
    last = store.get("last")
    prev = last.get("sample") if isinstance(last, dict) else None
    if isinstance(prev, dict) and _timestamp(prev) is not None and _timestamp(prev) == _timestamp(cur):
        cached = last.get("results") if isinstance(last, dict) else None
        if isinstance(cached, dict):
            idle_cached = last.get("idle") if isinstance(last.get("idle"), list) else []
            return dict(cached), list(idle_cached)

    if isinstance(prev, dict):
        ts_prev, ts_cur = _timestamp(prev), _timestamp(cur)
        if ts_prev is not None and ts_cur is not None and ts_cur < ts_prev:
            prev = None

    def _run(previous: Mapping[str, int] | None) -> tuple[dict[str, float], list[str]]:
        res: dict[str, float] = {}
        idle: list[str] = []
        for prop, *_ in _VALUES:
            try:
                value = compute_value(prop, types, cur, previous)
            except _NoRequests:
                idle.append(prop)
                continue
            if value is not None:
                res[prop] = value
        return res, idle

    try:
        results, idle = _run(prev if isinstance(prev, dict) else None)
    except _CounterReset:
        results, idle = _run(None)

    store["last"] = {"sample": dict(cur), "results": dict(results), "idle": list(idle), "time": time.time()}
    return results, idle


def _levels(params: Mapping[str, Any], key: str) -> Any:
    levels = params.get(key)
    if not isinstance(levels, (tuple, list)) or len(levels) != 2:
        return None
    kind, value = levels
    if kind == "no_levels":
        return ("no_levels", None)
    if kind == "fixed" and isinstance(value, (tuple, list)) and len(value) == 2:
        return ("fixed", (float(value[0]), float(value[1])))
    if kind == "predictive":
        return (kind, value)
    return None


def check_win_smb_shares(item: str, params: Mapping[str, Any], section: SmbSection) -> CheckResult:
    if section.error:
        yield Result(state=State.UNKNOWN, summary=f"Agent plug-in error: {section.error}")
        return
    sample = section.shares.get(item)
    if sample is None:
        return  # item not found -> UNKNOWN by Checkmk

    path = section.paths.get(item)
    if path:
        yield Result(state=State.OK, notice=f"Path: {path}")
    if section.source == "wmi":
        yield Result(
            state=State.OK,
            notice="Source: WMI fallback - on some servers this does not follow the real SMB traffic",
        )
    elif section.source:
        yield Result(state=State.OK, notice="Source: Windows performance counters")

    store = get_value_store()
    values, idle = compute_values(section.types, sample, store)

    shown = False
    for prop, key, metric, label, render_func, in_summary in _VALUES:
        if prop in idle:
            shown = True
            if in_summary:
                yield Result(state=State.OK, summary=f"{label}: no requests")
            else:
                yield Result(state=State.OK, notice=f"{label}: no requests")
            continue
        if prop not in values:
            continue
        shown = True
        yield from check_levels(
            values[prop],
            levels_upper=_levels(params, key),
            metric_name=metric,
            render_func=render_func,
            label=label,
            boundaries=(0.0, None),
            notice_only=not in_summary,
        )

    if not shown:
        if not section.types:
            yield Result(state=State.UNKNOWN, summary="No counter types reported by the agent plug-in")
        else:
            yield Result(state=State.OK, summary="Initializing counters")


check_plugin_win_smb_shares = CheckPlugin(
    name="win_smb_shares",
    service_name="SMB Share %s",
    discovery_function=discover_win_smb_shares,
    discovery_ruleset_name="win_smb_shares_discovery",
    discovery_ruleset_type=RuleSetType.MERGED,
    discovery_default_parameters=DISCOVERY_DEFAULT,
    check_function=check_win_smb_shares,
    check_ruleset_name="win_smb_shares",
    check_default_parameters=CHECK_DEFAULT,
)
