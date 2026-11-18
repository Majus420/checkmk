#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# CheckMK 2.4 Check Plugin: mssql_version_check
#
# Author: Marius Gielnik (Comramo)
#
# IMPORTANT: This plugin does NOT define its own AgentSection for "mssql_instance".
# CheckMK ships a built-in AgentSection for that raw section name
# (cmk.plugins.mssql.agent_based.mssql_instance:agent_section_mssql_instance).
# Only one parse_function may exist per raw section name - declaring a second one
# here previously collided with it ("plug-in 'mssql_instance' already defined"),
# which silently broke the official "MS SQL: General State" check and the
# MSSQL HW/SW inventory on every host using this MKP.
#
# Instead, this plugin subscribes to the already-parsed official section
# (sections=["mssql_instance"]) and adapts its Mapping[str, Mapping[str, str]]
# format itself - exactly the pattern CheckMK's own docs describe for extending
# an existing section ("other check plug-ins can also subscribe to this section").
#
# Official section content per instance (see cmk/plugins/mssql/agent_based/mssql_instance.py):
#   state               "1" = connected ok, "0"/missing = connection failed
#   error_msg           connection error text (only meaningful when state != "1")
#   config_version      RTM version from the registry (always present if config line was sent)
#   config_edition      edition string from the registry
#   details_version     actual live version queried from the running instance (preferred)
#   details_edition      patch label (e.g. "RTM") - despite the name, NOT a SQL edition
#   details_edition_long  the actual SQL edition string (e.g. "Standard Edition (64-bit)")
#
# Build data source: Microsoft Learn (official)
#   https://learn.microsoft.com/en-us/troubleshoot/sql/releases/sqlserver-{year}/build-versions
#
# Two build numbers are cached per version:
#   cu:     Latest Cumulative Update only
#   cu_gdr: Latest CU + GDR (highest available build incl. security patches)
#
# Item = instance name (e.g. "MSSQLSERVER", "DIAMANTP")
# Service name: "MSSQL <instance> Version"

from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.request
from collections.abc import Mapping
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from cmk.agent_based.v2 import (
    CheckPlugin,
    CheckResult,
    DiscoveryResult,
    Result,
    Service,
    State,
)

# Matches the official mssql_instance.py Section type exactly.
OfficialSection = Mapping[str, Mapping[str, str]]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_YEAR_TO_PRODUCT: Dict[str, str] = {
    "2025": "SQL Server 2025",
    "2022": "SQL Server 2022",
    "2019": "SQL Server 2019",
    "2017": "SQL Server 2017",
    "2016": "SQL Server 2016",
    "2014": "SQL Server 2014",
}

_MAJOR_TO_YEAR: Dict[str, str] = {
    "17": "2025",
    "16": "2022",
    "15": "2019",
    "14": "2017",
    "13": "2016",
    "12": "2014",
}

_SQL_VERSIONS: List[str] = ["2014", "2016", "2017", "2019", "2022", "2025"]

_MSLEARN_URL = (
    "https://learn.microsoft.com/en-us/troubleshoot/sql/releases"
    "/sqlserver-{year}/build-versions"
)

_CACHE_FILENAME        = "var/check_mk/mssql_latest_builds.json"
_CACHE_MAX_AGE_SECONDS = 24 * 60 * 60
_HTTP_TIMEOUT          = 15

# Cache behaviour
_CACHE_SCHEMA          = 2
_RETRY_FAILED_SECONDS  = 30 * 60      # do not hammer Microsoft after a failed fetch
_LOCK_STALE_SECONDS    = 180
_FETCH_BUDGET_SECONDS  = 60           # max total time one refresh may take

_BUILD_RE  = re.compile(r"\b(1[2-7]\.0\.\d{3,}\.\d+)\b")
_CU_NAME_RE = re.compile(r"^CU\s*\d+(?:\s*\([^)]*\))?$", re.IGNORECASE)
_ROW_RE    = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_CELL_RE   = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
_TAG_RE    = re.compile(r"<[^>]+>")


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class MSSQLInstanceInfo(NamedTuple):
    instance: str
    version:  str
    edition:  str
    patch:    str
    year:     str
    source:   str  # "details" or "config"
    connection_error: str = ""  # set when the agent failed to query the live instance


# ---------------------------------------------------------------------------
# Cache + fetch
# ---------------------------------------------------------------------------

def _cache_path() -> str:
    omd_root = os.environ.get("OMD_ROOT", "")
    return os.path.join(omd_root, _CACHE_FILENAME)


def _version_tuple(version_str: str) -> Tuple[int, ...]:
    try:
        return tuple(int(x) for x in version_str.split("."))
    except (ValueError, AttributeError):
        return (0,)


def _cell_text(raw: str) -> str:
    text = html.unescape(_TAG_RE.sub("", raw))
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _parse_builds(content: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse (latest_cu, latest_cu_gdr) from a build-versions page.

    Tolerant: table rows are split first, cell attributes/whitespace/nbsp are
    ignored. CU row = first cell "CUnn [(Latest)]" (no GDR); the second cell is
    the build number. CU+GDR = highest build number in the second column of
    any row.
    """
    cu: List[str] = []
    allb: List[str] = []
    for row in _ROW_RE.findall(content):
        cells = [_cell_text(c) for c in _CELL_RE.findall(row)]
        if len(cells) < 2:
            continue
        m = _BUILD_RE.fullmatch(cells[1])
        if not m:
            continue
        allb.append(m.group(1))
        if _CU_NAME_RE.match(cells[0]):
            cu.append(m.group(1))
    return (
        max(cu, key=_version_tuple) if cu else None,
        max(allb, key=_version_tuple) if allb else None,
    )


def _fetch_latest_builds(year: str) -> Tuple[Optional[str], Optional[str]]:
    """Returns (latest_cu, latest_cu_gdr) for the given SQL Server year.
    HTTP redirects (Learn -> support.microsoft.com) are followed."""
    url = _MSLEARN_URL.format(year=year)
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; CheckMK/1.0)",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            content = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None, None
    return _parse_builds(content)


def _read_cache(path: str) -> Dict[str, Any]:
    """Read cache; anything unusable (missing, corrupt, old format) -> {}."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_cache_atomic(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "{}.{}.tmp".format(path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _try_lock(lock_path: str) -> bool:
    try:
        if os.path.exists(lock_path) and time.time() - os.path.getmtime(lock_path) > _LOCK_STALE_SECONDS:
            os.unlink(lock_path)
    except OSError:
        pass
    try:
        os.close(os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        return True
    except OSError:
        return False


def _year_entry_ok(entry: Any) -> bool:
    return isinstance(entry, dict) and bool(entry.get("cu_gdr") or entry.get("cu"))


def _year_is_fresh(entry: Any, now: float) -> bool:
    return (
        _year_entry_ok(entry)
        and isinstance(entry.get("_ts"), (int, float))
        and now - entry["_ts"] <= _CACHE_MAX_AGE_SECONDS
    )


def _load_or_refresh_cache(
    needed_year: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Per-year self-healing cache.

    - A year is refreshed when missing, in old format, or older than 24h.
    - Failed years keep their previous (stale) value; failed years without any
      value are retried at most every 30 minutes.
    - Only one process refreshes at a time (lock file); others use the cache.
    - The file is written atomically and never loses years already known.
    """
    path = _cache_path()
    now = time.time()
    data = _read_cache(path)
    failed: Dict[str, Any] = data.get("_failed") if isinstance(data.get("_failed"), dict) else {}

    years = [needed_year] if needed_year else list(_SQL_VERSIONS)
    todo = [
        y for y in years
        if not _year_is_fresh(data.get(y), now)
        and not (isinstance(failed.get(y), (int, float)) and now - failed[y] < _RETRY_FAILED_SECONDS)
    ]

    if todo:
        lock_path = path + ".lock"
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except OSError:
            pass
        if _try_lock(lock_path):
            try:
                data = _read_cache(path)  # re-read: another process may have just finished
                failed = data.get("_failed") if isinstance(data.get("_failed"), dict) else {}
                start = time.time()
                changed = False
                for y in todo:
                    if _year_is_fresh(data.get(y), time.time()):
                        continue
                    if time.time() - start > _FETCH_BUDGET_SECONDS:
                        break
                    cu, cu_gdr = _fetch_latest_builds(y)
                    if cu or cu_gdr:
                        entry: Dict[str, Any] = {"_ts": time.time()}
                        if cu:
                            entry["cu"] = cu
                        if cu_gdr:
                            entry["cu_gdr"] = cu_gdr
                        data[y] = entry
                        failed.pop(y, None)
                    else:
                        failed[y] = time.time()
                    changed = True
                if changed:
                    data["_schema"] = _CACHE_SCHEMA
                    data["_failed"] = failed
                    data["_fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    try:
                        _write_cache_atomic(path, data)
                    except OSError:
                        pass
            finally:
                try:
                    os.unlink(lock_path)
                except OSError:
                    pass
        else:
            data = _read_cache(path)

    if needed_year:
        entry = data.get(needed_year)
        if not _year_entry_ok(entry):
            return None, (
                "No build data for SQL Server {} available (fetch from Microsoft failed or "
                "is in progress; retry in a few minutes)".format(needed_year)
            )
        if not _year_is_fresh(entry, now):
            return data, "Build data for SQL Server {} is older than 24h (refresh failed, using stale data)".format(needed_year)
    return data, None


# ---------------------------------------------------------------------------
# Adapt the official mssql_instance section to our own model.
# This replaces the old parse_function - it is called directly from
# discovery/check instead of being registered via AgentSection, so it never
# competes with the built-in parser for the "mssql_instance" raw section.
# ---------------------------------------------------------------------------

def _extract_instance_info(instance_id: str, attrs: Mapping[str, str]) -> Optional[MSSQLInstanceInfo]:
    has_details = "details_version" in attrs
    raw_version = attrs.get("details_version") or attrs.get("config_version")
    if not raw_version:
        return None

    # Robust extraction of the standalone version string (e.g. 17.0.4055.5).
    # Prevents strings with nested hyphens/KB details from breaking the major version logic.
    version_match = re.search(r"\b(1[2-7]\.0\.\d+\.\d+)\b", raw_version)
    version = version_match.group(1) if version_match else raw_version

    major = version.split(".")[0]
    year  = _MAJOR_TO_YEAR.get(major)
    if not year:
        return None

    source  = "details" if has_details else "config"
    edition = attrs.get("details_edition_long") or attrs.get("config_edition", "")
    # NB: the official section names the patch label (e.g. "RTM") "details_edition" -
    # the real SQL edition string lives in "details_edition_long".
    patch   = attrs.get("details_edition", "") if has_details else ""

    connection_error = ""
    if not has_details and attrs.get("state") != "1":
        message = attrs.get("error_msg", "")
        error_match = re.search(r"ERROR:\s*(.+)$", message)
        connection_error = error_match.group(1).strip() if error_match else (message or "connection failed")

    return MSSQLInstanceInfo(
        instance=instance_id, version=version, edition=edition,
        patch=patch, year=year, source=source, connection_error=connection_error,
    )


def _build_instances(section: OfficialSection) -> Dict[str, MSSQLInstanceInfo]:
    result: Dict[str, MSSQLInstanceInfo] = {}
    for instance_id, attrs in section.items():
        info = _extract_instance_info(instance_id, attrs)
        if info is not None:
            result[instance_id] = info
    return result


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_mssql_version_check(section: OfficialSection) -> DiscoveryResult:
    for instance in _build_instances(section):
        yield Service(item=instance)


# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------

def check_mssql_version_check(
    item: str,
    params: Dict[str, Any],
    section: OfficialSection,
) -> CheckResult:
    instances = _build_instances(section)

    if item not in instances:
        yield Result(state=State.UNKNOWN, summary="Instance {} not found in agent data".format(item))
        return

    info    = instances[item]
    version = info.version
    year    = info.year
    edition = info.edition or _YEAR_TO_PRODUCT.get(year, "SQL Server {}".format(year))
    patch   = info.patch

    if patch:
        version_display = "Microsoft SQL Server {} ({}) ({})".format(year, patch, version)
    else:
        version_display = "Microsoft SQL Server {} ({})".format(year, version)

    if edition:
        version_display = "{} - {}".format(version_display, edition)

    summary_base = "Version: {}".format(version_display)

    cache, cache_error = _load_or_refresh_cache(year)

    if cache_error and cache is None:
        yield Result(state=State.UNKNOWN, summary="{} | {}".format(summary_base, cache_error))
        return

    year_data = cache.get(year) if cache else None  # type: ignore[union-attr]
    if not year_data or not isinstance(year_data, dict):
        yield Result(
            state=State.UNKNOWN,
            summary="{} | No entry for SQL Server {} in cache".format(summary_base, year),
        )
        return

    # Determine which build target to use
    build_target = params.get("build_target", "cu_gdr")
    latest_build: Optional[str] = year_data.get(build_target) or year_data.get("cu_gdr") or year_data.get("cu")
    build_target_label = "CU + GDR" if build_target == "cu_gdr" else "CU"

    if not latest_build:
        yield Result(
            state=State.UNKNOWN,
            summary="{} | No build data for SQL Server {}".format(summary_base, year),
        )
        return

    installed_tuple = _version_tuple(version)
    try:
        latest_tuple = tuple(int(x) for x in latest_build.split("."))
    except ValueError:
        yield Result(
            state=State.WARN,
            summary="{} | Latest build '{}' not parseable".format(summary_base, latest_build),
        )
        return

    if installed_tuple >= latest_tuple:
        state   = State.OK
        verdict = "Up to date (latest {}: {})".format(build_target_label, latest_build)
    else:
        levels_mode = params.get("levels_mode", "warn_if_outdated")
        state   = State.CRIT if levels_mode == "crit_if_outdated" else State.WARN
        verdict = "Update available - latest {}: {}".format(build_target_label, latest_build)

    yield Result(state=state, summary="{} | {}".format(summary_base, verdict))

    if info.source == "config":
        if info.connection_error:
            yield Result(
                state=State.WARN,
                notice="Agent could not query live version (using RTM from registry instead): {}".format(
                    info.connection_error
                ),
            )
        else:
            yield Result(
                state=State.OK,
                notice="Version source: mssql_instance config line (version may reflect RTM, not actual CU)",
            )

    if cache_error:
        yield Result(state=State.WARN, notice=cache_error)

    if year_data.get("cu"):
        yield Result(state=State.OK, notice="Latest CU:       {}".format(year_data["cu"]))
    if year_data.get("cu_gdr"):
        yield Result(state=State.OK, notice="Latest CU + GDR: {}".format(year_data["cu_gdr"]))
    yield Result(state=State.OK, notice="Installed build: {}".format(version))
    yield Result(state=State.OK, notice="Build data source: learn.microsoft.com (official)")


# ---------------------------------------------------------------------------
# Registration
#
# Deliberately NO AgentSection() here - we subscribe to the section the
# built-in cmk.plugins.mssql.agent_based.mssql_instance plugin already
# registers for raw section "mssql_instance" (parsed_section_name defaults
# to the same name since the built-in doesn't override it).
# ---------------------------------------------------------------------------

check_plugin_mssql_version_check = CheckPlugin(
    name="mssql_version_check",
    sections=["mssql_instance"],
    service_name="MSSQL %s Version",
    discovery_function=discover_mssql_version_check,
    check_function=check_mssql_version_check,
    check_default_parameters={"levels_mode": "warn_if_outdated", "build_target": "cu_gdr"},
    check_ruleset_name="mssql_version_check",
)
