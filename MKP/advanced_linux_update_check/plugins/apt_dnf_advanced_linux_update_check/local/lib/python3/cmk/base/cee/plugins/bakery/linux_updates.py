#!/usr/bin/env python3
"""
linux_updates - Agent Bakery plug-in

Author:   Marius Gielnik
Project:  https://github.com/Majus420/checkmk/tree/main/plugins/apt_dnf_advanced_linux_update_check
License:  GPL-2.0-or-later

Rule:     "APT/DNF/Zypper: Linux update check (agent plug-in)" (rule set agent_config:linux_updates)
Deploys:  plugins/linux_updates           (sync: every agent call,
                                          async: plugins/<interval>/linux_updates)
          /etc/check_mk/linux_updates.cfg (refresh, min_refresh, refresh_timeout)
Conf:     {"deployment": ("asynchronous", 3600.0) | ("synchronous", None) | ("do_not_deploy", None),
           "refresh": "auto" | "never", "min_refresh": 14400.0, "refresh_timeout": 300.0}
"""

from pathlib import Path
from typing import Any

try:
    from cmk.base.cee.plugins.bakery.bakery_api.v1 import (  # type: ignore[import-not-found]
        OS,
        FileGenerator,
        Plugin,
        PluginConfig,
        register,
    )
except ImportError:
    from cmk.base.plugins.bakery.bakery_api.v1 import (
        OS,
        FileGenerator,
        Plugin,
        PluginConfig,
        register,
    )


def get_linux_updates_files(conf: Any) -> FileGenerator:
    if not isinstance(conf, dict):
        return
    mode, value = conf.get("deployment", ("asynchronous", 3600.0))
    if mode == "do_not_deploy":
        return
    interval = int(value) if mode == "asynchronous" and value else None

    yield Plugin(
        base_os=OS.LINUX,
        source=Path("linux_updates"),
        interval=interval,
    )
    yield PluginConfig(
        base_os=OS.LINUX,
        lines=[
            f"refresh={conf.get('refresh', 'auto')}",
            f"min_refresh={max(3600, int(conf.get('min_refresh', 14400)))}",
            f"refresh_timeout={int(conf.get('refresh_timeout', 300))}",
        ],
        target=Path("linux_updates.cfg"),
        include_header=True,
    )


register.bakery_plugin(
    name="linux_updates",
    files_function=get_linux_updates_files,
)
