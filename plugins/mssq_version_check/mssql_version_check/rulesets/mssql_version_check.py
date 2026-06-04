#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# CheckMK 2.4 Ruleset: mssql_version_check
from cmk.rulesets.v1 import Help, Title
from cmk.rulesets.v1.form_specs import (
    DefaultValue,
    DictElement,
    Dictionary,
    SingleChoice,
    SingleChoiceElement,
    String,
)
from cmk.rulesets.v1.rule_specs import CheckParameters, HostAndItemCondition, Topic
def _parameter_form() -> Dictionary:
    return Dictionary(
        title=Title("MSSQL Version Check Parameters"),
        help_text=Help(
            "Configure the behavior when a SQL Server update is available. "
            "The check reads the installed version from the win_wmi_software section "
            "(Microsoft SQL Server <year> Setup package) and compares it against the "
            "latest build fetched from a public Google Spreadsheet. "
            "The cache is self-refreshing — no cronjob required."
        ),
        elements={
            "levels_mode": DictElement(
                parameter_form=SingleChoice(
                    title=Title("State when an update is available"),
                    help_text=Help(
                        "Choose whether to report WARN or CRIT when the installed "
                        "SQL Server version is older than the latest available build."
                    ),
                    elements=[
                        SingleChoiceElement(
                            name="crit_if_outdated",
                            title=Title("CRIT — installed version is outdated"),
                        ),
                        SingleChoiceElement(
                            name="warn_if_outdated",
                            title=Title("WARN — installed version is outdated"),
                        ),
                    ],
                    prefill=DefaultValue("warn_if_outdated"),
                ),
                required=False,
            ),
        },
    )
rule_spec_mssql_version_check = CheckParameters(
    name="mssql_version_check",
    title=Title("MSSQL Version (online update check)"),
    topic=Topic.APPLICATIONS,
    parameter_form=_parameter_form,
    condition=HostAndItemCondition(
        item_title=Title("SQL Server Year"),
        item_form=String(
            help_text=Help(
                "The SQL Server year as discovered — e.g. 2022, 2019, 2017. "
                "Leave empty to match all versions."
            ),
        ),
    ),
)
