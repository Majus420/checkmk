#!/usr/bin/env python3
"""
win_smb_shares - Agent Bakery rule

Author:   Marius Gielnik
Project:  https://github.com/Majus420/checkmk/tree/main/MKP/windows_smb_share_performance
License:  GPL-2.0-or-later

Setup > Agents > Windows, Linux, Solaris, AIX > Agent rules >
"Windows: SMB share performance (agent plug-in)"
Consumed by ~/local/lib/python3/cmk/base/cee/plugins/bakery/win_smb_shares.py
"""

from cmk.rulesets.v1 import Help, Title
from cmk.rulesets.v1.form_specs import (
    CascadingSingleChoice,
    CascadingSingleChoiceElement,
    DefaultValue,
    DictElement,
    Dictionary,
    FixedValue,
    TimeMagnitude,
    TimeSpan,
)
from cmk.rulesets.v1.form_specs.validators import NumberInRange
from cmk.rulesets.v1.rule_specs import AgentConfig, Topic


def _form() -> Dictionary:
    return Dictionary(
        help_text=Help(
            "Deploys the agent plug-in win_smb_shares.ps1. It reads the raw performance "
            "counters of \"SMB Server Shares\" through the Windows performance counters (one read per run). "
            "Synchronous execution is recommended: latency and queue values are averages "
            "between two agent runs, an asynchronous interval makes them coarser."
        ),
        elements={
            "deployment": DictElement(
                required=True,
                parameter_form=CascadingSingleChoice(
                    title=Title("Deployment type"),
                    elements=[
                        CascadingSingleChoiceElement(
                            name="synchronous",
                            title=Title("Deploy the plug-in and run it synchronously"),
                            parameter_form=FixedValue(value=None),
                        ),
                        CascadingSingleChoiceElement(
                            name="asynchronous",
                            title=Title("Deploy the plug-in and run it asynchronously"),
                            parameter_form=TimeSpan(
                                title=Title("Interval"),
                                displayed_magnitudes=[TimeMagnitude.MINUTE, TimeMagnitude.SECOND],
                                prefill=DefaultValue(300.0),
                                custom_validate=(NumberInRange(min_value=60.0),),
                            ),
                        ),
                        CascadingSingleChoiceElement(
                            name="do_not_deploy",
                            title=Title("Do not deploy the plug-in"),
                            parameter_form=FixedValue(value=None),
                        ),
                    ],
                    prefill=DefaultValue("synchronous"),
                ),
            ),
            "timeout": DictElement(
                parameter_form=TimeSpan(
                    title=Title("Plug-in timeout"),
                    help_text=Help("Maximum runtime of the plug-in. Default of the agent: 60 seconds."),
                    displayed_magnitudes=[TimeMagnitude.SECOND],
                    prefill=DefaultValue(30.0),
                    custom_validate=(NumberInRange(min_value=5.0, max_value=600.0),),
                ),
            ),
        },
    )


rule_spec_win_smb_shares_bakery = AgentConfig(
    name="win_smb_shares",
    title=Title("Windows: SMB share performance (agent plug-in)"),
    topic=Topic.WINDOWS,
    parameter_form=_form,
)
