#!/bin/bash
# -----------------------------------------------------------------------------
# build_mkp.sh - builds the MKP "apt_dnf_advanced_linux_update_check" on a Checkmk site
#
# Author:   Marius Gielnik
# Project:  https://github.com/Majus420/checkmk/tree/main/plugins/apt_dnf_advanced_linux_update_check
# License:  GPL-2.0-or-later
#
# Run as:   site user of a Checkmk TEST site (2.5.0 or newer), from this directory
# Does:     1. copies local/ into ~/local (overwrites files of the same name)
#           2. mkp template -> ~/tmp/apt_dnf_advanced_linux_update_check.info
#           3. sets title, author, version, description, minimum version and
#              restricts the file list to the files of this directory
#           4. mkp package -> ~/var/check_mk/packages_local/<name>-<version>.mkp
# Note:     packaging on a central site distributes the package to remote sites.
# -----------------------------------------------------------------------------
set -euo pipefail

NAME="apt_dnf_advanced_linux_update_check"
VERSION="1.0.0"
HERE="$(cd "$(dirname "$0")" && pwd)"

[ -n "${OMD_ROOT:-}" ] || { echo "run as site user"; exit 1; }

cp -r "$HERE/local/." "$OMD_ROOT/local/"
chmod 755 "$OMD_ROOT/local/share/check_mk/agents/plugins/linux_updates" "$OMD_ROOT/local/bin/linux_updates_threatdb"

mkp template "$NAME" > "$OMD_ROOT/tmp/$NAME.info"

python3 - "$OMD_ROOT/tmp/$NAME.info" "$HERE" "$VERSION" <<'PY'
import ast, pathlib, sys
info_path, here, version = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
m = ast.literal_eval(info_path.read_text())
local = here / "local"
roots = {
    "cmk_addons_plugins": local / "lib/python3/cmk_addons/plugins",
    "agents": local / "share/check_mk/agents",
    "bin": local / "bin",
    "lib": local / "lib",
}
files = {}
for part, root in roots.items():
    items = [p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    if part == "lib":
        items = [p for p in items if "cmk_addons" not in p.parts]
    files[part] = sorted(str(p.relative_to(root)) for p in items)
m.update({
    "title": "APT/DNF/Zypper Advanced Linux Update Check",
    "author": "Marius Gielnik",
    "version": version,
    "version.min_required": "2.5.0",
    "version.usable_until": None,
    "download_url": "https://github.com/Majus420/checkmk/tree/main/plugins/apt_dnf_advanced_linux_update_check",
    "description": (
        "Package update monitoring for Debian/Ubuntu (apt: upgrade AND dist-upgrade), RHEL family/Fedora "
        "(dnf, yum: advisories with severity and CVEs) and SUSE (zypper: security patches). Tiers zero-day "
        "(CISA KEV) / critical (severity, EPSS) / security / normal, each with delay from first sight, state "
        "and escalation; zero-day and critical can be switched off. Reboot required, repository health, "
        "OS end of life, threat data updater. Agent Bakery rule with sync/async deployment."
    ),
    "files": files,
})
info_path.write_text(repr(m))
print({k: len(v) for k, v in files.items()})
PY

mkp package "$OMD_ROOT/tmp/$NAME.info"
ls -l "$OMD_ROOT/var/check_mk/packages_local/$NAME-$VERSION.mkp"
