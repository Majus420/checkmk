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
            "The check reads the installed version from the mssql_instance section "
            "and compares it against the latest build fetched from the official "
            "Microsoft Learn documentation. The cache is self-refreshing — no cronjob required."
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
                            name="warn_if_outdated",
                            title=Title("WARN — installed version is outdated"),
                        ),
                        SingleChoiceElement(
                            name="crit_if_outdated",
                            title=Title("CRIT — installed version is outdated"),
                        ),
                    ],
                    prefill=DefaultValue("warn_if_outdated"),
                ),
                required=False,
            ),
            "build_target": DictElement(
                parameter_form=SingleChoice(
                    title=Title("Build target for comparison"),
                    help_text=Help(
                        "Choose which build to use as the reference for the update check. "
                        "'Latest CU' compares against the latest Cumulative Update only. "
                        "'Latest CU + GDR' compares against the highest available build "
                        "including General Distribution Releases (security patches). "
                        "Hosts running only the latest CU without the GDR will be reported "
                        "as outdated when 'Latest CU + GDR' is selected."
                    ),
                    elements=[
                        SingleChoiceElement(
                            name="cu",
                            title=Title("Latest CU — Cumulative Update only"),
                        ),
                        SingleChoiceElement(
                            name="cu_gdr",
                            title=Title("Latest CU + GDR — highest available build incl. security patches"),
                        ),
                    ],
                    prefill=DefaultValue("cu_gdr"),
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
        item_title=Title("SQL Server Instance"),
        item_form=String(
            help_text=Help(
                "The SQL Server instance name as discovered — e.g. MSSQLSERVER, DIAMANTP. "
                "Leave empty to match all instances."
            ),
        ),
    ),
)
