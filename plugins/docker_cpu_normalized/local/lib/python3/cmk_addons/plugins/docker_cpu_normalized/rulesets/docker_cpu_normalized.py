#!/usr/bin/env python3
# Author: Marius Gielnik
# License: GNU General Public License v2 or later
"""Rulesets: check levels (WebUI) and agent bakery rule for docker_cpu_normalized."""

from cmk.rulesets.v1 import Help, Label, Title
from cmk.rulesets.v1.form_specs import (
    BooleanChoice,
    CascadingSingleChoice,
    CascadingSingleChoiceElement,
    DefaultValue,
    DictElement,
    Dictionary,
    FixedValue,
    LevelDirection,
    Percentage,
    SimpleLevels,
    TimeMagnitude,
    TimeSpan,
)
from cmk.rulesets.v1.rule_specs import (
    AgentConfig,
    CheckParameters,
    DiscoveryParameters,
    HostCondition,
    Topic,
)


def _time_levels_form() -> Dictionary:
    return Dictionary(
        elements={
            "threshold": DictElement(
                required=True,
                parameter_form=Percentage(
                    title=Title("High utilization at"),
                    prefill=DefaultValue(90.0),
                ),
            ),
            "warn_after": DictElement(
                required=True,
                parameter_form=TimeSpan(
                    title=Title("Warning after"),
                    displayed_magnitudes=[
                        TimeMagnitude.DAY,
                        TimeMagnitude.HOUR,
                        TimeMagnitude.MINUTE,
                        TimeMagnitude.SECOND,
                    ],
                    prefill=DefaultValue(5400.0),
                ),
            ),
            "crit_after": DictElement(
                required=True,
                parameter_form=TimeSpan(
                    title=Title("Critical after"),
                    displayed_magnitudes=[
                        TimeMagnitude.DAY,
                        TimeMagnitude.HOUR,
                        TimeMagnitude.MINUTE,
                        TimeMagnitude.SECOND,
                    ],
                    prefill=DefaultValue(10800.0),
                ),
            ),
        }
    )


def _parameter_form_check() -> Dictionary:
    return Dictionary(
        elements={
            "util": DictElement(
                required=True,
                parameter_form=SimpleLevels(
                    title=Title("Levels on normalized CPU utilization"),
                    help_text=Help(
                        "Utilization of the container in percent of the CPUs available to it: "
                        "the container CPU limit if one is set, otherwise all host CPUs."
                    ),
                    form_spec_template=Percentage(),
                    level_direction=LevelDirection.UPPER,
                    prefill_fixed_levels=DefaultValue(value=(80.0, 90.0)),
                ),
            ),
            "levels_over_time": DictElement(
                required=True,
                parameter_form=CascadingSingleChoice(
                    title=Title("Levels over an extended time period"),
                    help_text=Help(
                        "Alarm only if the normalized utilization stays at or above the "
                        "threshold for the given time. Short load peaks do not alarm."
                    ),
                    elements=[
                        CascadingSingleChoiceElement(
                            name="levels",
                            title=Title("Use levels over time"),
                            parameter_form=_time_levels_form(),
                        ),
                        CascadingSingleChoiceElement(
                            name="no_levels",
                            title=Title("No levels over time"),
                            parameter_form=FixedValue(value=None),
                        ),
                    ],
                    prefill=DefaultValue("levels"),
                ),
            ),
        }
    )


rule_spec_docker_cpu_normalized = CheckParameters(
    name="docker_cpu_normalized",
    title=Title("Docker container CPU utilization (normalized)"),
    topic=Topic.APPLICATIONS,
    parameter_form=_parameter_form_check,
    condition=HostCondition(),
)


def _parameter_form_bakery() -> Dictionary:
    return Dictionary(
        title=Title("Docker container CPU utilization (normalized)"),
        help_text=Help(
            "Deploys the agent plug-in docker_cpu_normalized (Linux and Windows). "
            "Docker must be installed on the host; no other dependencies."
        ),
        elements={
            "interval": DictElement(
                required=False,
                parameter_form=TimeSpan(
                    title=Title("Run asynchronously, cache for"),
                    displayed_magnitudes=[TimeMagnitude.MINUTE, TimeMagnitude.SECOND],
                    prefill=DefaultValue(60.0),
                ),
            ),
        },
    )


rule_spec_docker_cpu_normalized_bakery = AgentConfig(
    name="docker_cpu_normalized",
    title=Title("Docker container CPU utilization (normalized)"),
    topic=Topic.APPLICATIONS,
    parameter_form=_parameter_form_bakery,
)


def _parameter_form_discovery() -> Dictionary:
    return Dictionary(
        elements={
            "create_from_builtin": DictElement(
                required=True,
                parameter_form=BooleanChoice(
                    title=Title("Create the service from the standard Docker data"),
                    label=Label("Create the service Docker CPU utilization"),
                    help_text=Help(
                        "Uses the data the standard Docker monitoring already delivers "
                        "(piggyback data of mk_docker.py), no agent plug-in is needed. "
                        "Applies to Docker container hosts only. Hosts that receive the "
                        "section of the agent plug-in docker_cpu_normalized always get "
                        "the service."
                    ),
                    prefill=DefaultValue(False),
                ),
            ),
        }
    )


rule_spec_docker_cpu_normalized_discovery = DiscoveryParameters(
    name="docker_cpu_normalized_discovery",
    title=Title("Docker container CPU utilization (normalized)"),
    topic=Topic.APPLICATIONS,
    parameter_form=_parameter_form_discovery,
)
