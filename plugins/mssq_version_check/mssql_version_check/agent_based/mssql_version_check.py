#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# CheckMK 2.4 Check Plugin: mssql_version_check
#
# Source: mssql_instance section
#   <instance>|config|<version>|<edition>|          <- older/RTM version
#   <instance>|details|<version>|<patch>|<edition>  <- actual installed version (preferred)
#
# Build data source: Microsoft Learn (official)
#   https://learn.microsoft.com/en-us/troubleshoot/sql/releases/sqlserver-{year}/build-versions
#
# Item = instance name (e.g. "MSSQLSERVER", "DIAMANTP", "CITRIX")
# Service name: "MSSQL <instance> Version"

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from cmk.agent_based.v2 import (
    AgentSection,
    CheckPlugin,
    CheckResult,
    DiscoveryResult,
    Result,
    Service,
    State,
    StringTable,
)

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

# Official Microsoft Learn build version pages
_MSLEARN_URL = (
    "https://learn.microsoft.com/en-us/troubleshoot/sql/releases"
    "/sqlserver-{year}/build-versions"
)

_CACHE_FILENAME        = "var/check_mk/mssql_latest_builds.json"
_CACHE_MAX_AGE_SECONDS = 24 * 60 * 60
_HTTP_TIMEOUT          = 20

# Matches table rows like:
#   | CU23 (Latest) | 16.0.4236.2 | ...
#   | CU22 + GDR (Latest) | 16.0.4230.2 | ...
_LATEST_ROW_RE = re.compile(
    r"<td>[^<]*\(Latest\)[^<]*</td>\s*<td>([\d]+\.[\d]+\.[\d]+\.[\d]+)</td>",
    re.IGNORECASE,
)

# Fallback: match any build version in a table row (to find highest)
_BUILD_RE = re.compile(r"<td>(1[2-7]\.0\.\d+\.\d+)</td>")


# ---------------------------------------------------------------------------
# Parsed type
# ---------------------------------------------------------------------------

class MSSQLInstanceInfo(NamedTuple):
    instance: str
    version:  str
    edition:  str
    patch:    str
    year:     str
    source:   str  # "details" or "config"


# ---------------------------------------------------------------------------
# Cache + fetch from Microsoft Learn
# ---------------------------------------------------------------------------

def _cache_path() -> str:
    omd_root = os.environ.get("OMD_ROOT", "")
    return os.path.join(omd_root, _CACHE_FILENAME)


def _version_tuple(version_str: str) -> Tuple[int, ...]:
    try:
        return tuple(int(x) for x in version_str.split("."))
    except (ValueError, AttributeError):
        return (0,)


def _fetch_latest_build(year: str) -> Optional[str]:
    url = _MSLEARN_URL.format(year=year)
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; CheckMK/1.0)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            content = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None

    # First try: find row explicitly marked as (Latest)
    match = _LATEST_ROW_RE.search(content)
    if match:
        return match.group(1)

    # Fallback: find all build numbers for this major version and return highest
    builds = [m.group(1) for m in _BUILD_RE.finditer(content)]
    if builds:
        return max(builds, key=_version_tuple)

    return None


def _load_or_refresh_cache() -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    path     = _cache_path()
    do_fetch = False

    if not os.path.exists(path):
        do_fetch = True
    else:
        age = time.time() - os.path.getmtime(path)
        if age > _CACHE_MAX_AGE_SECONDS:
            do_fetch = True

    if do_fetch:
        result: Dict[str, str] = {}
        for year in _SQL_VERSIONS:
            build = _fetch_latest_build(year)
            if build:
                result[year] = build

        if not result:
            if os.path.exists(path):
                try:
                    with open(path, encoding="utf-8") as fh:
                        data = json.load(fh)
                    return data, "WARNING: Could not refresh build data (using stale cache)"
                except (OSError, json.JSONDecodeError):
                    pass
            return None, (
                "Could not fetch build data from Microsoft Learn "
                "(check internet access from CMK server to learn.microsoft.com)"
            )

        result["_fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(result, fh, indent=2)
        except OSError:
            pass

        return result, None

    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data, None
    except (OSError, json.JSONDecodeError) as exc:
        return None, "Cache file not readable: {}".format(exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_mssql_prefix(instance: str) -> str:
    if instance.upper().startswith("MSSQL_"):
        return instance[6:]
    return instance


# ---------------------------------------------------------------------------
# Parse mssql_instance section
# ---------------------------------------------------------------------------

def parse_mssql_version_check(string_table: StringTable) -> Dict[str, MSSQLInstanceInfo]:
    details: Dict[str, MSSQLInstanceInfo] = {}
    config:  Dict[str, MSSQLInstanceInfo] = {}

    for row in string_table:
        if len(row) < 3:
            continue
        instance = _strip_mssql_prefix(row[0].strip())
        row_type = row[1]
        version  = row[2].strip()
        if not version:
            continue
        major = version.split(".")[0]
        year  = _MAJOR_TO_YEAR.get(major)
        if not year:
            continue

        if row_type == "details":
            patch   = row[3].strip() if len(row) > 3 else ""
            edition = row[4].strip() if len(row) > 4 else ""
            info = MSSQLInstanceInfo(
                instance=instance, version=version, edition=edition,
                patch=patch, year=year, source="details",
            )
            if instance not in details or _version_tuple(version) > _version_tuple(details[instance].version):
                details[instance] = info

        elif row_type == "config":
            edition = row[3].strip() if len(row) > 3 else ""
            info = MSSQLInstanceInfo(
                instance=instance, version=version, edition=edition,
                patch="", year=year, source="config",
            )
            if instance not in config or _version_tuple(version) > _version_tuple(config[instance].version):
                config[instance] = info

    result: Dict[str, MSSQLInstanceInfo] = {}
    for inst in set(details) | set(config):
        result[inst] = details.get(inst) or config[inst]  # type: ignore[assignment]
    return result


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_mssql_version_check(
    section: Dict[str, MSSQLInstanceInfo],
) -> DiscoveryResult:
    for instance in section:
        yield Service(item=instance)


# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------

def check_mssql_version_check(
    item: str,
    params: Dict[str, Any],
    section: Dict[str, MSSQLInstanceInfo],
) -> CheckResult:
    if item not in section:
        yield Result(state=State.UNKNOWN, summary="Instance {} not found in agent data".format(item))
        return

    info    = section[item]
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

    cache, cache_error = _load_or_refresh_cache()

    if cache_error and cache is None:
        yield Result(state=State.UNKNOWN, summary="{} | {}".format(summary_base, cache_error))
        return

    latest_build: Optional[str] = cache.get(year) if cache else None  # type: ignore[union-attr]
    if not latest_build:
        yield Result(
            state=State.UNKNOWN,
            summary="{} | No entry for SQL Server {} in cache".format(summary_base, year),
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
        verdict = "Up to date (latest build: {})".format(latest_build)
    else:
        levels_mode = params.get("levels_mode", "warn_if_outdated")
        state   = State.CRIT if levels_mode == "crit_if_outdated" else State.WARN
        verdict = "Update available - latest build: {}".format(latest_build)

    yield Result(state=state, summary="{} | {}".format(summary_base, verdict))

    if info.source == "config":
        yield Result(
            state=State.OK,
            notice="Version source: mssql_instance config line (version may reflect RTM, not actual CU)",
        )

    if cache_error:
        yield Result(state=State.WARN, notice=cache_error)

    yield Result(state=State.OK, notice="Latest available build ({}): {}".format(year, latest_build))
    yield Result(state=State.OK, notice="Installed build: {}".format(version))
    yield Result(
        state=State.OK,
        notice="Build data source: learn.microsoft.com (official)",
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

agent_section_mssql_version_check = AgentSection(
    name="mssql_instance",
    parsed_section_name="mssql_version_check",
    parse_function=parse_mssql_version_check,
)

check_plugin_mssql_version_check = CheckPlugin(
    name="mssql_version_check",
    service_name="MSSQL %s Version",
    discovery_function=discover_mssql_version_check,
    check_function=check_mssql_version_check,
    check_default_parameters={"levels_mode": "warn_if_outdated"},
    check_ruleset_name="mssql_version_check",
)
