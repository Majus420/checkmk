#!/usr/bin/env python3
# Author: Marius Gielnik
# License: GNU General Public License v2 or later
"""Agent bakery plug-in: deploys docker_cpu_normalized on Linux and Windows."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cmk.bakery.v1 import create_bakery_plugin, FileGenerator, OS, Plugin


def get_docker_cpu_normalized_files(conf: Mapping[str, Any] | None) -> FileGenerator:
    if conf is None:
        return
    interval = conf.get("interval")
    interval = int(interval) if interval else None
    yield Plugin(base_os=OS.LINUX, source=Path("docker_cpu_normalized"), interval=interval)
    yield Plugin(base_os=OS.WINDOWS, source=Path("docker_cpu_normalized.ps1"), interval=interval)


bakery_plugin_docker_cpu_normalized = create_bakery_plugin(
    name="docker_cpu_normalized",
    files_function=get_docker_cpu_normalized_files,
)
