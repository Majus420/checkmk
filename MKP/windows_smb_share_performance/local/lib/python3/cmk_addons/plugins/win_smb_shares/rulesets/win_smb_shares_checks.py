#!/usr/bin/env python3
"""
win_smb_shares - check parameters and discovery rule

Author:   Marius Gielnik
Project:  https://github.com/Majus420/checkmk/tree/main/MKP/windows_smb_share_performance
License:  GPL-2.0-or-later

Setup > Services > Service monitoring rules > "Windows SMB share performance"
Setup > Services > Discovery rules > "Windows SMB share discovery"
Consumed by cmk_addons/plugins/win_smb_shares/agent_based/win_smb_shares.py
"""

from cmk.rulesets.v1 import Help, Label, Title
from cmk.rulesets.v1.form_specs import (
    DefaultValue,
    DictElement,
    Dictionary,
    Float,
    Integer,
    LevelDirection,
    List,
    MatchingScope,
    RegularExpression,
    SimpleLevels,
    String,
    TimeMagnitude,
    TimeSpan,
)
from cmk.rulesets.v1.rule_specs import CheckParameters, DiscoveryParameters, HostAndItemCondition, Topic


def _latency(title: str, help_text: str, warn: float, crit: float) -> DictElement:
    return DictElement(
        parameter_form=SimpleLevels[float](
            title=Title(title),  # pylint: disable=localization-checker
            help_text=Help(help_text),  # pylint: disable=localization-checker
            level_direction=LevelDirection.UPPER,
            form_spec_template=TimeSpan(displayed_magnitudes=[TimeMagnitude.SECOND, TimeMagnitude.MILLISECOND]),
            prefill_fixed_levels=DefaultValue((warn, crit)),
        )
    )


def _queue(title: str, help_text: str, warn: float, crit: float) -> DictElement:
    return DictElement(
        parameter_form=SimpleLevels[float](
            title=Title(title),  # pylint: disable=localization-checker
            help_text=Help(help_text),  # pylint: disable=localization-checker
            level_direction=LevelDirection.UPPER,
            form_spec_template=Float(),
            prefill_fixed_levels=DefaultValue((warn, crit)),
        )
    )


def _check_form() -> Dictionary:
    return Dictionary(
        help_text=Help(
            "Upper levels for the SMB server share performance counters of Windows "
            "(performance object \"SMB Server Shares\"). All values are averages over the check "
            "interval. Defaults without any rule: data/read/write latency 20/50 ms, average and "
            "current data queue length 2/5; all other values (requests/s, throughput, open files, "
            "connections, ...) are only recorded as metrics unless set here. "
            "Select \"No levels\" to switch a default off."
        ),
        elements={
            "latency_data": _latency(
                "Data latency (Avg. sec/Data Request)",
                "Average time per read or write request on the share.",
                0.02,
                0.05,
            ),
            "latency_read": _latency(
                "Read latency (Avg. sec/Read)", "Average time per read request on the share.", 0.02, 0.05
            ),
            "latency_write": _latency(
                "Write latency (Avg. sec/Write)", "Average time per write request on the share.", 0.02, 0.05
            ),
            "latency_request": _latency(
                "Request latency (Avg. sec/Request)",
                "Average time per request of any kind, including metadata requests.",
                0.02,
                0.05,
            ),
            "queue_avg_data": _queue(
                "Average data queue length (Avg. Data Queue Length)",
                "Average number of read and write requests queued on the share.",
                2.0,
                5.0,
            ),
            "queue_avg_read": _queue(
                "Average read queue length (Avg. Read Queue Length)",
                "Average number of read requests queued on the share.",
                2.0,
                5.0,
            ),
            "queue_avg_write": _queue(
                "Average write queue length (Avg. Write Queue Length)",
                "Average number of write requests queued on the share.",
                2.0,
                5.0,
            ),
            "queue_current_data": _queue(
                "Current data queue length (Current Data Queue Length)",
                "Number of read and write requests queued at the moment of the check.",
                2.0,
                5.0,
            ),
            "open_files": DictElement(
                parameter_form=SimpleLevels[int](
                    title=Title("Open files (Current Open File Count)"),
                    help_text=Help("Number of files currently open on the share."),
                    level_direction=LevelDirection.UPPER,
                    form_spec_template=Integer(),
                    prefill_fixed_levels=DefaultValue((5000, 10000)),
                )
            ),
            "tree_connects": DictElement(
                parameter_form=SimpleLevels[int](
                    title=Title("Connections (Tree Connect Count)"),
                    help_text=Help("Number of client connections to the share."),
                    level_direction=LevelDirection.UPPER,
                    form_spec_template=Integer(),
                    prefill_fixed_levels=DefaultValue((500, 1000)),
                )
            ),
            "pending_requests": _queue(
                "Pending requests (Current Pending Requests)",
                "Number of requests waiting to be processed at the moment of the check.",
                5.0,
                10.0,
            ),
        },
    )


rule_spec_win_smb_shares = CheckParameters(
    name="win_smb_shares",
    title=Title("Windows SMB share performance"),
    topic=Topic.STORAGE,
    parameter_form=_check_form,
    condition=HostAndItemCondition(item_title=Title("Share name")),
)


def _regex_list(title: str, help_text: str) -> List[str]:
    return List(
        title=Title(title),  # pylint: disable=localization-checker
        help_text=Help(help_text),  # pylint: disable=localization-checker
        element_template=RegularExpression(predefined_help_text=MatchingScope.INFIX),
        add_element_label=Label("Add pattern"),
    )


def _discovery_form() -> Dictionary:
    return Dictionary(
        help_text=Help(
            "Selects the shares for which a service \"SMB Share <name>\" is created. "
            "The share name is matched as reported by Windows, without the leading \\\\*\\. "
            "Without this rule all shares are discovered except the administrative shares Windows "
            "creates itself (drive shares like C$, ADMIN$, IPC$, print$) and _Total. Hidden user "
            "shares such as home$ are discovered. Name and path filters are combined: a share must "
            "pass all configured filters. Usually the path list alone is enough."
        ),
        elements={
            "include": DictElement(
                parameter_form=_regex_list(
                    "Only discover shares matching",
                    "Regular expressions (infix match, case insensitive). If set, only matching shares are discovered.",
                )
            ),
            "exclude": DictElement(
                parameter_form=List(
                    title=Title("Do not discover shares matching"),
                    help_text=Help(
                        "Regular expressions (infix match, case insensitive). If this option is not set, the administrative "
                        "shares (^[A-Za-z]\\$$, ^(ADMIN|IPC|print)\\$$) and ^_Total$ are excluded. If set, "
                        "only these patterns apply."
                    ),
                    element_template=RegularExpression(predefined_help_text=MatchingScope.INFIX),
                    add_element_label=Label("Add pattern"),
                )
            ),
            "paths": DictElement(
                parameter_form=List(
                    title=Title("Only discover shares with these local paths"),
                    help_text=Help(
                        "Local folder of the share on the Windows server, as plain text - no regular "
                        "expression, e.g. E:\\home or D:\\Shares\\Public. Case and a trailing backslash "
                        "do not matter. A trailing * selects all shares below a folder: E:\\* for all "
                        "shares on drive E:. Shares without a known path are not discovered when this is set."
                    ),
                    element_template=String(),
                    add_element_label=Label("Add path"),
                )
            ),
        },
    )


rule_spec_win_smb_shares_discovery = DiscoveryParameters(
    name="win_smb_shares_discovery",
    title=Title("Windows SMB share discovery"),
    topic=Topic.STORAGE,
    parameter_form=_discovery_form,
)
