#!/usr/bin/env python3
"""
build_mkp.py - builds windows_smb_share_performance-<version>.mkp from ./local

Author:   Marius Gielnik
Project:  https://github.com/Majus420/checkmk/tree/main/MKP/windows_smb_share_performance
License:  GPL-2.0-or-later

Run:      python3 build_mkp.py            (any Linux host with Python 3.9+, no Checkmk needed)
Output:   dist/windows_smb_share_performance-<version>.mkp
Format:   same as cmk-mkp-tool 3.0.0: outer tar.gz with info (Python repr), info.json
          and one uncompressed tar per part (cmk_addons_plugins, agents, lib),
          members without prefix, owner root/root, 644 / 755 for the agent plug-in.
"""

import io
import json
import pathlib
import pprint
import tarfile
import time

NAME = "windows_smb_share_performance"
VERSION = "1.4.0"
HERE = pathlib.Path(__file__).resolve().parent
LOCAL = HERE / "local"

PARTS = {
    "cmk_addons_plugins": LOCAL / "lib/python3/cmk_addons/plugins",
    "agents": LOCAL / "share/check_mk/agents",
    "lib": LOCAL / "lib",
}

INFO = {
    "title": "Windows SMB Share Performance (latency, queue length)",
    "name": NAME,
    "description": (
        "Monitors SMB shares on Windows file servers per share: latency per data, read, write and any "
        "request, average data/read/write queue length, current data queue length, pending requests, requests/s, throughput, open files and connections "
        "(performance object 'SMB Server Shares'). The agent plug-in reads the raw counters through the .NET performance counters (same data as perfmon), "
        "which works on any Windows language; rates are computed on the Checkmk server according to the "
        "counter type reported by Windows. Default levels (latency 20/50 ms, queue 2/5), adjustable per share. Shares selectable by plain local path (E:\\home, E:\\*) or by name, local path shown per service. "
        "Graphs, perfometer, Agent Bakery rule (synchronous or asynchronous). "
        "Requires Windows Server 2012 or newer.\n\n"
        "Überwacht SMB-Freigaben auf Windows-Fileservern je Freigabe: Latenz pro Daten-, Lese-, Schreib- "
        "und Gesamtanfrage, durchschnittliche Daten-/Lese-/Schreib-Warteschlange, aktuelle "
        "Warteschlange, ausstehende Anfragen, Anfragen/s, Durchsatz, offene Dateien und Verbindungen (Leistungsobjekt 'SMB Server Shares'). Das Agent-Plugin "
        "liest die Rohzähler sprachunabhängig über die .NET-Leistungsindikatoren (wie perfmon), die Raten berechnet der Checkmk-Server anhand des "
        "von Windows gemeldeten Zählertyps. Standard-Schwellwerte (Latenz 20/50 ms, Warteschlange 2/5), je Freigabe anpassbar. Freigaben per lokalem Pfad im Klartext (E:\\home, E:\\*) oder per Name auswählbar, Pfad je Service sichtbar. Discovery-Filter per regulärem "
        "Ausdruck, Graphen, Perf-O-Meter, Agent-Bakery-Regel. Ab Windows Server 2012."
    ),
    "version": VERSION,
    "version.packaged": "cmk-mkp-tool 3.0.0",
    "version.min_required": "2.5.0",
    "version.usable_until": None,
    "author": "Marius Gielnik",
    "download_url": "https://github.com/Majus420/checkmk/tree/main/MKP/windows_smb_share_performance",
}


def collect() -> dict:
    files = {}
    for part, root in PARTS.items():
        items = [p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
        if part == "lib":
            items = [p for p in items if "cmk_addons" not in p.parts]
        files[part] = sorted(str(p.relative_to(root)) for p in items)
    return files


def add_bytes(tar: tarfile.TarFile, name: str, data: bytes, mode: int, mtime: float) -> None:
    ti = tarfile.TarInfo(name)
    ti.size, ti.mode, ti.mtime = len(data), mode, int(mtime)
    ti.uid = ti.gid = 0
    ti.uname = ti.gname = "root"
    tar.addfile(ti, io.BytesIO(data))


def main() -> None:
    files = collect()
    info = dict(INFO, files=files)
    now = time.time()
    out_dir = HERE / "dist"
    out_dir.mkdir(exist_ok=True)
    target = out_dir / f"{NAME}-{VERSION}.mkp"

    with tarfile.open(target, "w:gz", format=tarfile.GNU_FORMAT) as outer:
        add_bytes(outer, "info", (pprint.pformat(info) + "\n").encode(), 0o644, now)
        add_bytes(outer, "info.json", json.dumps(info).encode(), 0o644, now)
        for part, root in PARTS.items():
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as inner:
                for rel in files[part]:
                    src = root / rel
                    mode = 0o755 if part == "agents" else 0o644
                    add_bytes(inner, rel, src.read_bytes(), mode, src.stat().st_mtime)
            add_bytes(outer, f"{part}.tar", buf.getvalue(), 0o644, now)

    print({k: len(v) for k, v in files.items()})
    print(target)


if __name__ == "__main__":
    main()
