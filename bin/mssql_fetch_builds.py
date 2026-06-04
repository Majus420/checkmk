#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mssql_fetch_builds.py
=====================
Fetches the latest available Microsoft SQL Server build numbers from the
official Microsoft Learn documentation and writes them to the CheckMK cache.

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

_LATEST_ROW_RE = re.compile(
    r"<td>[^<]*\(Latest\)[^<]*</td>\s*<td>([\d]+\.[\d]+\.[\d]+\.[\d]+)</td>",
    re.IGNORECASE,
)
_BUILD_RE = re.compile(r"<td>(1[2-7]\.0\.\d+\.\d+)</td>")


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


def fetch_latest_build(year: str) -> Optional[str]:
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
        return None

    # Try (Latest) marker first
    match = _LATEST_ROW_RE.search(content)
    if match:
        return match.group(1)

    # Fallback: highest build number found on page
    builds = [m.group(1) for m in _BUILD_RE.finditer(content)]
    if builds:
        return max(builds, key=version_tuple)

    log("  WARNING: No valid build numbers found for SQL Server {}".format(year))
    return None


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

    result: Dict[str, str] = {}
    errors: List[str]      = []

    for year in SQL_VERSIONS:
        log("  Fetching SQL Server {}...".format(year))
        build = fetch_latest_build(year)
        if build:
            result[year] = build
            log("  SQL Server {}: latest build = {}".format(year, build))
        else:
            errors.append(year)

    if not result:
        log("ERROR: Could not fetch any build data - aborting without writing cache")
        return 1

    if errors:
        log("WARNING: Could not fetch data for: {}".format(", ".join(errors)))

    result["_fetched_at"] = datetime.now(timezone.utc).isoformat()

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
