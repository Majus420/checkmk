#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mssql_fetch_builds.py
=====================
Fetches the latest available Microsoft SQL Server build numbers from the
official Microsoft Learn documentation and writes them to the CheckMK cache.

Two build numbers are cached per version:
  - latest_cu:     Latest Cumulative Update (CU) only
  - latest_cu_gdr: Latest CU + GDR (highest available build incl. security patches)

Source:
  https://learn.microsoft.com/en-us/troubleshoot/sql/releases/sqlserver-{year}/build-versions

Cache file written to:
  $OMD_ROOT/var/check_mk/mssql_latest_builds.json

Usage:
  python3 mssql_fetch_builds.py          # normal run, writes cache
  python3 mssql_fetch_builds.py --show   # print result, do not write
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SQL_VERSIONS: List[str] = ["2014", "2016", "2017", "2019", "2022", "2025"]

MSLEARN_URL = (
    "https://learn.microsoft.com/en-us/troubleshoot/sql/releases"
    "/sqlserver-{year}/build-versions"
)

CACHE_RELPATH = "var/check_mk/mssql_latest_builds.json"
HTTP_TIMEOUT  = 20

# Matches CU-only rows (no GDR): <td>CU25</td> or <td>CU32 (Latest)</td>
# Excludes rows containing "GDR"
_CU_BUILD_RE = re.compile(
    r"<td>CU\d+(?:\s*\([^)]*\))?</td>\s*<td>(1[2-7]\.0\.\d+\.\d+)</td>",
    re.IGNORECASE,
)

# Matches all builds (CU, CU+GDR, GDR) — just any valid build number in a <td>
_ALL_BUILD_RE = re.compile(r"<td>(1[2-7]\.0\.(\d{3,})\.\d+)</td>")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("[{}] {}".format(ts, msg), flush=True)


def version_tuple(v: str) -> Tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


def fetch_builds(year: str) -> Tuple[Optional[str], Optional[str]]:
    """Returns (latest_cu, latest_cu_gdr) for the given SQL Server year."""
    url = MSLEARN_URL.format(year=year)
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; CheckMK/1.0)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            content = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        log("  ERROR fetching data for {}: {}".format(year, exc))
        return None, None

    # Latest CU only (no GDR)
    cu_builds = [m.group(1) for m in _CU_BUILD_RE.finditer(content)]
    latest_cu = max(cu_builds, key=version_tuple) if cu_builds else None

    # Highest build overall (CU + GDR)
    all_builds = [m.group(1) for m in _ALL_BUILD_RE.finditer(content)]
    latest_cu_gdr = max(all_builds, key=version_tuple) if all_builds else None

    if not latest_cu and not latest_cu_gdr:
        log("  WARNING: No valid build numbers found for SQL Server {}".format(year))

    return latest_cu, latest_cu_gdr


def cache_path() -> str:
    omd_root = os.environ.get("OMD_ROOT", os.path.expanduser("~"))
    return os.path.join(omd_root, CACHE_RELPATH)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch latest MSSQL builds from Microsoft Learn"
    )
    parser.add_argument("--show", action="store_true", help="Print result only, do not write cache")
    args = parser.parse_args()

    log("Starting MSSQL build fetch (source: learn.microsoft.com)")
    log("Fetching SQL Server versions: {}".format(", ".join(SQL_VERSIONS)))

    result: Dict[str, Dict[str, str]] = {}
    errors: List[str] = []

    for year in SQL_VERSIONS:
        log("  Fetching SQL Server {}...".format(year))
        latest_cu, latest_cu_gdr = fetch_builds(year)
        if latest_cu or latest_cu_gdr:
            result[year] = {}
            if latest_cu:
                result[year]["cu"] = latest_cu
                log("  SQL Server {}: latest CU       = {}".format(year, latest_cu))
            if latest_cu_gdr:
                result[year]["cu_gdr"] = latest_cu_gdr
                log("  SQL Server {}: latest CU + GDR = {}".format(year, latest_cu_gdr))
        else:
            errors.append(year)

    if not result:
        log("ERROR: Could not fetch any build data - aborting without writing cache")
        return 1

    if errors:
        log("WARNING: Could not fetch data for: {}".format(", ".join(errors)))

    result["_fetched_at"] = datetime.now(timezone.utc).isoformat()  # type: ignore[assignment]

    if args.show:
        print(json.dumps(result, indent=2))
        return 0

    path = cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)

    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
        log("Cache written to: {}".format(path))
    except OSError as exc:
        log("ERROR writing cache file {}: {}".format(path, exc))
        return 1

    log("Done{}.".format(" with warnings" if errors else ""))
    return 2 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
