#!/usr/bin/env python3
"""
linux_updates - metrics, graphs and perfometers

Author:   Marius Gielnik
Project:  https://github.com/Majus420/checkmk/tree/main/MKP/advanced_linux_update_check
License:  GPL-2.0-or-later
"""

from cmk.graphing.v1 import Title
from cmk.graphing.v1.graphs import Graph, MinimalRange
from cmk.graphing.v1.metrics import (
    Color,
    DecimalNotation,
    Metric,
    StrictPrecision,
    TimeNotation,
    Unit,
)
from cmk.graphing.v1.perfometers import Closed, FocusRange, Open, Perfometer

_COUNT = Unit(DecimalNotation(""), StrictPrecision(0))
_TIME = Unit(TimeNotation())

metric_linux_updates_zero_day = Metric(
    name="linux_updates_zero_day",
    title=Title("Pending updates: zero-day (actively exploited)"),
    unit=_COUNT,
    color=Color.DARK_RED,
)
metric_linux_updates_critical = Metric(
    name="linux_updates_critical",
    title=Title("Pending updates: critical"),
    unit=_COUNT,
    color=Color.RED,
)
metric_linux_updates_security = Metric(
    name="linux_updates_security",
    title=Title("Pending updates: security"),
    unit=_COUNT,
    color=Color.ORANGE,
)
metric_linux_updates_normal = Metric(
    name="linux_updates_normal",
    title=Title("Pending updates: normal"),
    unit=_COUNT,
    color=Color.BLUE,
)
metric_linux_updates_security_age = Metric(
    name="linux_updates_security_age",
    title=Title("Age of the oldest pending security update"),
    unit=_TIME,
    color=Color.PURPLE,
)
metric_linux_updates_reboot_age = Metric(
    name="linux_updates_reboot_age",
    title=Title("Reboot pending since"),
    unit=_TIME,
    color=Color.GRAY,
)
metric_linux_updates_cache_age = Metric(
    name="linux_updates_cache_age",
    title=Title("Age of the package metadata"),
    unit=_TIME,
    color=Color.CYAN,
)
metric_linux_updates_autoremove = Metric(
    name="linux_updates_autoremove",
    title=Title("Autoremovable packages"),
    unit=_COUNT,
    color=Color.BROWN,
)

graph_linux_updates_pending = Graph(
    name="linux_updates_pending",
    title=Title("Pending updates by tier"),
    compound_lines=[
        "linux_updates_zero_day",
        "linux_updates_critical",
        "linux_updates_security",
        "linux_updates_normal",
    ],
    minimal_range=MinimalRange(0, 5),
)
graph_linux_updates_security_age = Graph(
    name="linux_updates_security_age",
    title=Title("Age of the oldest pending security update"),
    simple_lines=["linux_updates_security_age"],
    minimal_range=MinimalRange(0, 86400),
)

perfometer_linux_updates_pending = Perfometer(
    name="linux_updates_pending",
    focus_range=FocusRange(Closed(0), Open(50)),
    segments=[
        "linux_updates_zero_day",
        "linux_updates_critical",
        "linux_updates_security",
        "linux_updates_normal",
    ],
)
perfometer_linux_updates_reboot_age = Perfometer(
    name="linux_updates_reboot_age",
    focus_range=FocusRange(Closed(0), Open(604800)),
    segments=["linux_updates_reboot_age"],
)
perfometer_linux_updates_cache_age = Perfometer(
    name="linux_updates_cache_age",
    focus_range=FocusRange(Closed(0), Open(604800)),
    segments=["linux_updates_cache_age"],
)
