#!/usr/bin/env python3
"""
linux_updates - check parameter rule sets

Author:   Marius Gielnik
Project:  https://github.com/Majus420/checkmk/tree/main/plugins/apt_dnf_advanced_linux_update_check
License:  GPL-2.0-or-later

Setup > Services > Service monitoring rules > Operating System Resources:
  "APT/DNF/Zypper: pending updates"    -> service "Linux Pending Updates"
  "APT/DNF/Zypper: reboot required"    -> service "Linux Reboot Required"
  "APT/DNF/Zypper: repository health"  -> service "Linux Repository Health"
"""

from cmk.rulesets.v1 import Help, Title
from cmk.rulesets.v1.form_specs import (
    CascadingSingleChoice,
    CascadingSingleChoiceElement,
    DefaultValue,
    FixedValue,
    DictElement,
    Dictionary,
    Integer,
    LevelDirection,
    List,
    MatchingScope,
    MultipleChoice,
    MultipleChoiceElement,
    Percentage,
    RegularExpression,
    ServiceState,
    SimpleLevels,
    TimeMagnitude,
    TimeSpan,
)
from cmk.rulesets.v1.form_specs.validators import NumberInRange
from cmk.rulesets.v1.rule_specs import CheckParameters, HostCondition, Topic

_MAG = [TimeMagnitude.DAY, TimeMagnitude.HOUR, TimeMagnitude.MINUTE]
_MAG_DAYS = [TimeMagnitude.DAY, TimeMagnitude.HOUR]


def _state(title: str, default: int, help_text: str | None = None) -> ServiceState:
    return ServiceState(
        title=Title(title),  # pylint: disable=localization-checker
        help_text=Help(help_text) if help_text else None,  # pylint: disable=localization-checker
        prefill=DefaultValue(default),
    )


def _age_levels(title: str, warn: float, crit: float) -> SimpleLevels[float]:
    return SimpleLevels[float](
        title=Title(title),  # pylint: disable=localization-checker
        form_spec_template=TimeSpan(displayed_magnitudes=_MAG_DAYS),
        level_direction=LevelDirection.UPPER,
        prefill_fixed_levels=DefaultValue((warn, crit)),
    )


def _tier(title: str, help_text: str, state: int, delay: float) -> Dictionary:
    return Dictionary(
        title=Title(title),  # pylint: disable=localization-checker
        help_text=Help(help_text),  # pylint: disable=localization-checker
        elements={
            "delay": DictElement(
                required=True,
                parameter_form=TimeSpan(
                    title=Title("Report after the update has been pending for"),
                    displayed_magnitudes=_MAG,
                    prefill=DefaultValue(delay),
                    custom_validate=(NumberInRange(min_value=0),),
                ),
            ),
            "state": DictElement(
                required=True,
                parameter_form=_state("State once this time has passed", state),
            ),
            "escalate": DictElement(
                required=False,
                parameter_form=Dictionary(
                    title=Title("Escalate if still pending"),
                    elements={
                        "after": DictElement(
                            required=True,
                            parameter_form=TimeSpan(
                                title=Title("Pending for at least"),
                                displayed_magnitudes=_MAG,
                                prefill=DefaultValue(604800.0),
                            ),
                        ),
                        "state": DictElement(
                            required=True,
                            parameter_form=_state("State", 2),
                        ),
                    },
                ),
            ),
        },
    )


def _switchable(title: str, tier: Dictionary) -> CascadingSingleChoice:
    return CascadingSingleChoice(
        title=Title(title),  # pylint: disable=localization-checker
        help_text=Help(
            "If switched off, updates of this tier fall through to the next tier "
            "(critical, then security)."
        ),
        elements=[
            CascadingSingleChoiceElement(
                name="enabled",
                title=Title("Evaluate this tier"),
                parameter_form=tier,
            ),
            CascadingSingleChoiceElement(
                name="disabled",
                title=Title("Do not evaluate this tier"),
                parameter_form=FixedValue(value=None),
            ),
        ],
        prefill=DefaultValue("enabled"),
    )


# ------------------------------------------------------------ pending updates


def _form_updates() -> Dictionary:
    return Dictionary(
        help_text=Help(
            "Every pending update is put into one tier. The time counts from the moment the "
            "agent plug-in first saw the update (package and target version) on the host. "
            "Zero-day and critical need the threat data on the site "
            "(linux_updates_threatdb); without it, updates fall back to security/normal."
        ),
        elements={
            "tier_zero_day": DictElement(
                required=True,
                parameter_form=_switchable(
                    "Zero-day: fixes an actively exploited vulnerability (CISA KEV)",
                    _tier(
                        "Settings",
                        "The update fixes at least one CVE listed in the CISA Known Exploited "
                        "Vulnerabilities catalog.",
                        2,
                        0.0,
                    ),
                ),
            ),
            "tier_critical": DictElement(
                required=True,
                parameter_form=_switchable(
                    "Critical: fixes a high-severity or likely exploited vulnerability",
                    _tier(
                        "Settings",
                        "The update fixes a CVE whose severity (distribution advisory or "
                        "OSV) is one of the selected severities, or whose EPSS score reaches "
                        "the threshold.",
                        1,
                        14400.0,
                    ),
                ),
            ),
            "tier_security": DictElement(
                required=True,
                parameter_form=_tier(
                    "Security: security update",
                    "Any other security update: from a security repository (apt), named in a "
                    "security advisory (dnf/yum) or part of a security patch (zypper).",
                    1,
                    86400.0,
                ),
            ),
            "tier_normal": DictElement(
                required=True,
                parameter_form=_tier(
                    "Normal: all other updates",
                    "Updates without security relevance.",
                    0,
                    0.0,
                ),
            ),
            "critical_severities": DictElement(
                required=True,
                parameter_form=MultipleChoice(
                    title=Title("Severities counted as critical (important = high, moderate = medium)"),
                    elements=[
                        MultipleChoiceElement(name="critical", title=Title("critical")),
                        MultipleChoiceElement(name="high", title=Title("high")),
                        MultipleChoiceElement(name="medium", title=Title("medium")),
                    ],
                    prefill=DefaultValue(["critical", "high"]),
                ),
            ),
            "epss_threshold": DictElement(
                required=False,
                parameter_form=Percentage(
                    title=Title("EPSS score counted as critical from"),
                    help_text=Help(
                        "EPSS estimates the probability that a vulnerability is exploited "
                        "within the next 30 days. Minimum 1 %."
                    ),
                    prefill=DefaultValue(10.0),
                    custom_validate=(NumberInRange(min_value=1.0, max_value=100.0),),
                ),
            ),
            "removals_state": DictElement(
                required=True,
                parameter_form=_state("State if dist-upgrade would remove packages", 0),
            ),
            "withheld_state": DictElement(
                required=True,
                parameter_form=_state(
                    "State for packages kept back that cannot be installed", 0
                ),
            ),
            "held_state": DictElement(
                required=True,
                parameter_form=_state("State for held/locked packages (apt-mark hold, versionlock, zypper locks)", 0),
            ),
            "ignore": DictElement(
                required=False,
                parameter_form=List(
                    title=Title("Ignore packages"),
                    help_text=Help("Regular expressions matched against the package name."),
                    element_template=RegularExpression(
                        predefined_help_text=MatchingScope.INFIX,
                    ),
                ),
            ),
        },
    )


rule_spec_linux_updates_pending = CheckParameters(
    name="linux_updates_pending",
    title=Title("APT/DNF/Zypper: pending updates"),
    topic=Topic.OPERATING_SYSTEM,
    parameter_form=_form_updates,
    condition=HostCondition(),
)

# ------------------------------------------------------------ reboot required


def _form_reboot() -> Dictionary:
    return Dictionary(
        elements={
            "state": DictElement(
                required=True,
                parameter_form=_state("State if a reboot is required", 1),
            ),
            "escalate": DictElement(
                required=False,
                parameter_form=Dictionary(
                    title=Title("Escalate if the reboot is still pending"),
                    elements={
                        "after": DictElement(
                            required=True,
                            parameter_form=TimeSpan(
                                title=Title("Pending for at least"),
                                displayed_magnitudes=_MAG_DAYS,
                                prefill=DefaultValue(604800.0),
                            ),
                        ),
                        "state": DictElement(
                            required=True,
                            parameter_form=_state("State", 2),
                        ),
                    },
                ),
            ),
            "restart_state": DictElement(
                required=True,
                parameter_form=_state(
                    "State if services need a restart",
                    0,
                    "apt: needs needrestart on the host; dnf/yum: needs-restarting; zypper: zypper ps.",
                ),
            ),
        },
    )


rule_spec_linux_updates_reboot = CheckParameters(
    name="linux_updates_reboot",
    title=Title("APT/DNF/Zypper: reboot required"),
    topic=Topic.OPERATING_SYSTEM,
    parameter_form=_form_reboot,
    condition=HostCondition(),
)

# ---------------------------------------------------------- repository health


def _form_repos() -> Dictionary:
    return Dictionary(
        elements={
            "cache_age": DictElement(
                required=True,
                parameter_form=_age_levels("Age of the package metadata", 259200.0, 604800.0),
            ),
            "refresh_failed_state": DictElement(
                required=True,
                parameter_form=_state("State if the last metadata refresh failed", 1),
            ),
            "refresh_warnings_state": DictElement(
                required=True,
                parameter_form=_state("State if the last metadata refresh had warnings", 0),
            ),
            "errors_state": DictElement(
                required=True,
                parameter_form=_state("State on package manager errors", 1),
            ),
            "no_security_info_state": DictElement(
                required=True,
                parameter_form=_state(
                    "State if no security information is available",
                    1,
                    "apt: no security repository configured. dnf/yum: no advisory metadata "
                    "(e.g. CentOS Stream). zypper: no patch metadata. Without it no update is "
                    "ever classified as security.",
                ),
            ),
            "foreign_suite_state": DictElement(
                required=True,
                parameter_form=_state(
                    "State if Debian/Ubuntu repositories of a different release are configured (apt)",
                    1,
                ),
            ),
            "duplicate_sources_state": DictElement(
                required=True,
                parameter_form=_state("State if repositories are configured multiple times", 0),
            ),
            "legacy_keyring_state": DictElement(
                required=True,
                parameter_form=_state("State if the legacy keyring trusted.gpg is used (apt)", 0),
            ),
            "broken_packages_state": DictElement(
                required=True,
                parameter_form=_state(
                    "State on package database problems (dpkg --audit/apt-get check, dnf check, zypper verify)", 1
                ),
            ),
            "autoremove_levels": DictElement(
                required=False,
                parameter_form=SimpleLevels[int](
                    title=Title("Number of autoremovable packages"),
                    form_spec_template=Integer(),
                    level_direction=LevelDirection.UPPER,
                    prefill_fixed_levels=DefaultValue((10, 30)),
                ),
            ),
            "orphans_state": DictElement(
                required=True,
                parameter_form=_state("State if packages from no repository are installed", 0),
            ),
            "auto_missing_state": DictElement(
                required=True,
                parameter_form=_state(
                    "State if automatic updates are not installed or not enabled "
                    "(unattended-upgrades, dnf-automatic, yum-cron)",
                    0,
                ),
            ),
            "auto_errors_state": DictElement(
                required=True,
                parameter_form=_state("State on errors in the last unattended-upgrades run", 0),
            ),
            "auto_age": DictElement(
                required=False,
                parameter_form=_age_levels("Time since the last unattended-upgrades run", 172800.0, 604800.0),
            ),
            "last_upgrade_age": DictElement(
                required=False,
                parameter_form=_age_levels("Time since the last package change", 2592000.0, 7776000.0),
            ),
            "eol_state": DictElement(
                required=True,
                parameter_form=_state("State if the OS release is end of life", 1, "EOL dates from endoflife.date (threat data on the site), on Debian/Ubuntu also from distro-info."),
            ),
            "eol_warn_before": DictElement(
                required=False,
                parameter_form=TimeSpan(
                    title=Title("Warn before end of life"),
                    displayed_magnitudes=[TimeMagnitude.DAY],
                    prefill=DefaultValue(7776000.0),
                ),
            ),
            "threatdb_age": DictElement(
                required=True,
                parameter_form=_age_levels("Age of the threat data on the site", 172800.0, 604800.0),
            ),
            "threatdb_missing_state": DictElement(
                required=True,
                parameter_form=_state("State if the threat data is missing", 1),
            ),
        },
    )


rule_spec_linux_updates_repos = CheckParameters(
    name="linux_updates_repos",
    title=Title("APT/DNF/Zypper: repository health"),
    topic=Topic.OPERATING_SYSTEM,
    parameter_form=_form_repos,
    condition=HostCondition(),
)

