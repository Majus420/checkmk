#!/usr/bin/env python3
"""
linux_updates - Agent Bakery rule

Author:   Marius Gielnik
Project:  https://github.com/Majus420/checkmk/tree/main/MKP/advanced_linux_update_check
License:  GPL-2.0-or-later

Setup > Agents > Windows, Linux, Solaris, AIX > Agent rules >
"APT/DNF/Zypper: Linux update check (agent plug-in)"
Consumed by ~/local/lib/python3/cmk/base/cee/plugins/bakery/linux_updates.py
"""

from cmk.rulesets.v1 import Help, Title
from cmk.rulesets.v1.form_specs import (
    CascadingSingleChoice,
    CascadingSingleChoiceElement,
    DefaultValue,
    DictElement,
    Dictionary,
    FixedValue,
    SingleChoice,
    SingleChoiceElement,
    TimeMagnitude,
    TimeSpan,
)
from cmk.rulesets.v1.form_specs.validators import NumberInRange
from cmk.rulesets.v1.rule_specs import AgentConfig, Topic


def _migrate(value: object) -> dict:
    """Rules saved with the removed option "synchronous" become asynchronous, 1 hour."""
    if not isinstance(value, dict):
        return {}
    value = dict(value)
    deployment = value.get("deployment")
    if isinstance(deployment, tuple) and deployment and deployment[0] == "synchronous":
        value["deployment"] = ("asynchronous", 3600.0)
    return value


def _form() -> Dictionary:
    return Dictionary(
        migrate=_migrate,
        help_text=Help(
            "Deploys the agent plug-in linux_updates for Debian/Ubuntu (apt), RHEL family/Fedora (dnf, yum) and SUSE (zypper). It only reads the local package metadata, nothing is ever installed. The plug-in always runs "
            "asynchronously: it takes several seconds and may refresh the package metadata, "
            "which must never block the agent."
        ),
        elements={
            "deployment": DictElement(
                required=True,
                parameter_form=CascadingSingleChoice(
                    title=Title("Deployment type"),
                    elements=[
                        CascadingSingleChoiceElement(
                            name="asynchronous",
                            title=Title("Deploy the plug-in and run it asynchronously"),
                            parameter_form=TimeSpan(
                                title=Title("Interval for checking for updates"),
                                displayed_magnitudes=[
                                    TimeMagnitude.DAY,
                                    TimeMagnitude.HOUR,
                                    TimeMagnitude.MINUTE,
                                ],
                                prefill=DefaultValue(3600.0),
                                custom_validate=(NumberInRange(min_value=300.0),),
                            ),
                        ),
                        CascadingSingleChoiceElement(
                            name="do_not_deploy",
                            title=Title("Do not deploy the plug-in"),
                            parameter_form=FixedValue(value=None),
                        ),
                    ],
                    prefill=DefaultValue("asynchronous"),
                ),
            ),
            "refresh": DictElement(
                required=True,
                parameter_form=SingleChoice(
                    title=Title("Refresh package metadata (apt-get update, dnf makecache, zypper refresh)"),
                    help_text=Help(
                        "If enabled, the plug-in refreshes the metadata itself, but never more often "
                        "than the minimum interval - also when a mirror fails. A refresh done by "
                        "the system (apt-daily.timer, dnf-makecache.timer) counts as well."
                    ),
                    elements=[
                        SingleChoiceElement(
                            name="auto",
                            title=Title("Yes, respecting the minimum interval"),
                        ),
                        SingleChoiceElement(
                            name="never",
                            title=Title("No, use the lists refreshed by the system"),
                        ),
                    ],
                    prefill=DefaultValue("auto"),
                ),
            ),
            "min_refresh": DictElement(
                required=True,
                parameter_form=TimeSpan(
                    title=Title("Minimum interval between metadata refreshes"),
                    displayed_magnitudes=[TimeMagnitude.DAY, TimeMagnitude.HOUR, TimeMagnitude.MINUTE],
                    prefill=DefaultValue(14400.0),
                    custom_validate=(NumberInRange(min_value=3600.0),),
                ),
            ),
            "refresh_timeout": DictElement(
                required=True,
                parameter_form=TimeSpan(
                    title=Title("Timeout for the metadata refresh"),
                    displayed_magnitudes=[TimeMagnitude.MINUTE, TimeMagnitude.SECOND],
                    prefill=DefaultValue(300.0),
                    custom_validate=(NumberInRange(min_value=30.0, max_value=3600.0),),
                ),
            ),
        },
    )


rule_spec_linux_updates_bakery = AgentConfig(
    name="linux_updates",
    title=Title("APT/DNF/Zypper: Linux update check (agent plug-in)"),
    topic=Topic.LINUX,
    parameter_form=_form,
)
