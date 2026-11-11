#!/usr/bin/env python3
"""
win_smb_shares - Agent Bakery plug-in

Author:   Marius Gielnik
Project:  https://github.com/Majus420/checkmk/tree/main/MKP/windows_smb_share_performance
License:  GPL-2.0-or-later

Rule:     "Windows: SMB share performance (agent plug-in)" (rule set agent_config:win_smb_shares)
Deploys:  plugins\\win_smb_shares.ps1 (Windows agent)
Conf:     {"deployment": ("synchronous", None) | ("asynchronous", 300.0) | ("do_not_deploy", None),
           "timeout": 30.0 (optional)}
"""

from pathlib import Path
from typing import Any

try:
    from cmk.base.cee.plugins.bakery.bakery_api.v1 import (  # type: ignore[import-not-found]
        OS,
        FileGenerator,
        Plugin,
        register,
    )
except ImportError:
    from cmk.base.plugins.bakery.bakery_api.v1 import (  # type: ignore[import-not-found,no-redef]
        OS,
        FileGenerator,
        Plugin,
        register,
    )


def get_win_smb_shares_files(conf: Any) -> FileGenerator:
    if not isinstance(conf, dict):
        return
    deployment = conf.get("deployment", ("synchronous", None))
    if not isinstance(deployment, (tuple, list)) or not deployment:
        deployment = ("synchronous", None)
    mode = deployment[0]
    value = deployment[1] if len(deployment) > 1 else None
    if mode == "do_not_deploy":
        return

    timeout = conf.get("timeout")
    kwargs: dict[str, Any] = {}
    if isinstance(timeout, (int, float)) and timeout > 0:
        kwargs["timeout"] = int(timeout)
    if mode == "asynchronous":
        kwargs["interval"] = max(60, int(value or 300))
        kwargs["asynchronous"] = True

    yield Plugin(
        base_os=OS.WINDOWS,
        source=Path("win_smb_shares.ps1"),
        **kwargs,
    )


register.bakery_plugin(
    name="win_smb_shares",
    files_function=get_win_smb_shares_files,
)
