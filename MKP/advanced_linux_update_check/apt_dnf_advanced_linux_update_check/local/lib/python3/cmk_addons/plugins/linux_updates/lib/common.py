#!/usr/bin/env python3
"""
linux_updates - shared helpers (check plug-ins and threat data updater)

Author:   Marius Gielnik
Project:  https://github.com/Majus420/checkmk/tree/main/MKP/advanced_linux_update_check
License:  GPL-2.0-or-later

- dpkg version comparison (same algorithm as dpkg --compare-versions)
- location and loading of the threat database written by
  ~/local/bin/linux_updates_threatdb
- mapping of a host's OS to a threat database ecosystem
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

THREATDB_DIR = Path(os.environ.get("OMD_ROOT", "/omd/sites/unknown")) / "var/check_mk/linux_updates/threatdb"
META_FILE = "meta.json"

# --------------------------------------------------------------------- dpkg


def _order(char: str) -> int:
    if char == "~":
        return -1
    if "0" <= char <= "9":
        return 0
    if char.isascii() and char.isalpha():
        return ord(char)
    return ord(char) + 256


def _isdigit(char: str) -> bool:
    return "0" <= char <= "9"


def _verrevcmp(a: str, b: str) -> int:
    i = j = 0
    la, lb = len(a), len(b)
    while i < la or j < lb:
        first_diff = 0
        while (i < la and not _isdigit(a[i])) or (j < lb and not _isdigit(b[j])):
            ac = _order(a[i]) if i < la and not _isdigit(a[i]) else 0
            bc = _order(b[j]) if j < lb and not _isdigit(b[j]) else 0
            if ac != bc:
                return ac - bc
            if i < la and not _isdigit(a[i]):
                i += 1
            if j < lb and not _isdigit(b[j]):
                j += 1
        while i < la and a[i] == "0":
            i += 1
        while j < lb and b[j] == "0":
            j += 1
        while i < la and _isdigit(a[i]) and j < lb and _isdigit(b[j]):
            if not first_diff:
                first_diff = ord(a[i]) - ord(b[j])
            i += 1
            j += 1
        if i < la and _isdigit(a[i]):
            return 1
        if j < lb and _isdigit(b[j]):
            return -1
        if first_diff:
            return first_diff
    return 0


def _split(version: str) -> tuple[int, str, str]:
    version = version.strip()
    epoch = 0
    if ":" in version:
        head, version = version.split(":", 1)
        epoch = int(head) if head.isdigit() else 0
    if "-" in version:
        upstream, revision = version.rsplit("-", 1)
    else:
        upstream, revision = version, ""
    return epoch, upstream, revision


def vercmp(a: str, b: str) -> int:
    """<0 if a<b, 0 if equal, >0 if a>b (dpkg semantics)"""
    ea, ua, ra = _split(a)
    eb, ub, rb = _split(b)
    if ea != eb:
        return ea - eb
    res = _verrevcmp(ua, ub)
    if res:
        return res
    return _verrevcmp(ra, rb)


# ---------------------------------------------------------------- ecosystems

_UBUNTU_RE = re.compile(r"^Ubuntu:(\d+\.\d+)(?::LTS)?$")
_DEBIAN_RE = re.compile(r"^Debian:(\d+)$")


def ecosystem_from_osv(name: str) -> str | None:
    """OSV ecosystem string -> threat db key, None for unsupported (Pro/FIPS...)"""
    if m := _UBUNTU_RE.match(name):
        return f"ubuntu_{m.group(1)}"
    if m := _DEBIAN_RE.match(name):
        return f"debian_{m.group(1)}"
    return None


def ecosystem_from_host(os_id: str, version_id: str) -> str | None:
    os_id = os_id.lower()
    if os_id == "ubuntu" and re.match(r"^\d+\.\d+$", version_id):
        return f"ubuntu_{version_id}"
    if os_id == "debian" and version_id:
        return f"debian_{version_id.split('.')[0]}"
    return None


# ------------------------------------------------------------- threat data

_CACHE: dict[str, tuple[float, Any]] = {}


def _load_json(path: Path) -> Any:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    key = str(path)
    cached = _CACHE.get(key)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    _CACHE[key] = (mtime, data)
    return data


def load_meta() -> dict[str, Any] | None:
    data = _load_json(THREATDB_DIR / META_FILE)
    return data if isinstance(data, dict) else None


def load_ecosystem(eco: str) -> dict[str, list[list[Any]]] | None:
    """{source_package: [[fixed_version, cve, kev(0/1), severity, epss], ...]}"""
    data = _load_json(THREATDB_DIR / f"{eco}.json")
    if not isinstance(data, dict):
        return None
    pkgs = data.get("packages")
    return pkgs if isinstance(pkgs, dict) else None


def fixed_cves(
    db: dict[str, list[list[Any]]], source: str, installed: str, candidate: str
) -> list[tuple[str, bool, str, float]]:
    """CVEs fixed by updating source package from installed to candidate.

    Returns [(cve, kev, severity, epss)], an entry counts when
    installed < fixed_version <= candidate.
    """
    result: dict[str, tuple[str, bool, str, float]] = {}
    if not installed:
        return []
    for entry in db.get(source, ()):
        try:
            fixed, cve, kev, sev, epss = entry
        except ValueError:
            continue
        if vercmp(installed, fixed) < 0 <= vercmp(candidate, fixed):
            prev = result.get(cve)
            item = (cve, bool(kev), str(sev or ""), float(epss or 0.0))
            if prev is None or (item[1], item[3]) > (prev[1], prev[3]):
                result[cve] = item
    return sorted(result.values(), key=lambda x: (not x[1], -x[3], x[0]))


def load_cve_info() -> tuple[frozenset[str], dict[str, float]]:
    """(KEV CVE ids, EPSS scores >= 1 %) from cves.json"""
    data = _load_json(THREATDB_DIR / "cves.json")
    if not isinstance(data, dict):
        return frozenset(), {}
    cached = _CACHE.get("__cveinfo__")
    if cached and cached[1][0] is data:
        return cached[1][1], cached[1][2]
    kev = frozenset(data.get("kev", []))
    epss = {str(k): float(v) for k, v in (data.get("epss") or {}).items()}
    _CACHE["__cveinfo__"] = (0.0, (data, kev, epss))
    return kev, epss


SEVERITY_MAP = {
    "critical": "critical",
    "important": "high",
    "high": "high",
    "moderate": "medium",
    "medium": "medium",
    "low": "low",
    "negligible": "low",
}


def normalize_severity(value: str) -> str:
    return SEVERITY_MAP.get(value.strip().lower(), "")


# endoflife.date product per os-release ID
EOL_PRODUCTS = {
    "debian": "debian",
    "ubuntu": "ubuntu",
    "rhel": "rhel",
    "rocky": "rocky-linux",
    "almalinux": "almalinux",
    "ol": "oracle-linux",
    "fedora": "fedora",
    "sles": "sles",
    "sled": "sles",
    "opensuse-leap": "opensuse",
    "amzn": "amazon-linux",
}


def eol_product(os_id: str, version_id: str) -> str | None:
    os_id = os_id.lower()
    if os_id == "centos":
        return "centos" if version_id.split(".")[0] in ("6", "7") else "centos-stream"
    return EOL_PRODUCTS.get(os_id)


def lookup_eol(os_id: str, version_id: str) -> str | None:
    """EOL date (YYYY-MM-DD) from eol.json, None if unknown"""
    data = _load_json(THREATDB_DIR / "eol.json")
    product = eol_product(os_id, version_id)
    if not isinstance(data, dict) or not product:
        return None
    cycles = data.get("products", {}).get(product)
    if not isinstance(cycles, dict):
        return None
    for key in (version_id, version_id.split(".")[0]):
        value = cycles.get(key)
        if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            return value
    return None


# ------------------------------------------------------- automatic refresh

THREATDB_MAX_AGE = 6 * 3600  # refresh the threat data when older than this
TRIGGER_INTERVAL = 3600  # at most one start attempt per hour and site


def ensure_threatdb_fresh(now: float) -> None:
    """Start ~/local/bin/linux_updates_threatdb in the background when the
    threat data is missing or older than THREATDB_MAX_AGE.

    Called by the check plug-ins, so every site that monitors hosts keeps its
    own data current without cron or manual setup. At most one attempt per
    TRIGGER_INTERVAL; the updater itself holds a lock against parallel runs.
    """
    try:
        meta = THREATDB_DIR / META_FILE
        age = now - meta.stat().st_mtime if meta.exists() else float("inf")
        if age < THREATDB_MAX_AGE:
            return
        stamp = THREATDB_DIR.parent / "trigger.stamp"
        if stamp.exists() and now - stamp.stat().st_mtime < TRIGGER_INTERVAL:
            return
        updater = Path(os.environ.get("OMD_ROOT", "")) / "local/bin/linux_updates_threatdb"
        if not updater.is_file():
            return
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.touch()
        import subprocess  # pylint: disable=import-outside-toplevel

        subprocess.Popen(  # pylint: disable=consider-using-with
            [str(updater)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError:
        pass
