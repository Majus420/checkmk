#!/usr/bin/env python3
"""
win_smb_shares - metrics, graphs and perfometer

Author:   Marius Gielnik
Project:  https://github.com/Majus420/checkmk/tree/main/MKP/windows_smb_share_performance
License:  GPL-2.0-or-later
"""

from cmk.graphing.v1 import Title
from cmk.graphing.v1.graphs import Graph, MinimalRange
from cmk.graphing.v1.metrics import AutoPrecision, Color, DecimalNotation, IECNotation, Metric, StrictPrecision, TimeNotation, Unit
from cmk.graphing.v1.perfometers import Closed, FocusRange, Open, Perfometer

_TIME = Unit(TimeNotation())
_COUNT = Unit(DecimalNotation(""), AutoPrecision(2))
_RATE = Unit(DecimalNotation("/s"), AutoPrecision(2))
_BYTES_RATE = Unit(IECNotation("B/s"), AutoPrecision(2))
_INT = Unit(DecimalNotation(""), StrictPrecision(0))

metric_win_smb_share_latency_data = Metric(
    name="win_smb_share_latency_data",
    title=Title("SMB share data latency"),
    unit=_TIME,
    color=Color.BLUE,
)
metric_win_smb_share_latency_read = Metric(
    name="win_smb_share_latency_read",
    title=Title("SMB share read latency"),
    unit=_TIME,
    color=Color.GREEN,
)
metric_win_smb_share_latency_write = Metric(
    name="win_smb_share_latency_write",
    title=Title("SMB share write latency"),
    unit=_TIME,
    color=Color.ORANGE,
)
metric_win_smb_share_latency_request = Metric(
    name="win_smb_share_latency_request",
    title=Title("SMB share request latency (all requests)"),
    unit=_TIME,
    color=Color.PURPLE,
)
metric_win_smb_share_queue_avg_data = Metric(
    name="win_smb_share_queue_avg_data",
    title=Title("SMB share avg. data queue length"),
    unit=_COUNT,
    color=Color.BLUE,
)
metric_win_smb_share_queue_avg_read = Metric(
    name="win_smb_share_queue_avg_read",
    title=Title("SMB share avg. read queue length"),
    unit=_COUNT,
    color=Color.GREEN,
)
metric_win_smb_share_queue_avg_write = Metric(
    name="win_smb_share_queue_avg_write",
    title=Title("SMB share avg. write queue length"),
    unit=_COUNT,
    color=Color.ORANGE,
)
metric_win_smb_share_queue_current_data = Metric(
    name="win_smb_share_queue_current_data",
    title=Title("SMB share current data queue length"),
    unit=_COUNT,
    color=Color.DARK_BLUE,
)
metric_win_smb_share_pending_requests = Metric(
    name="win_smb_share_pending_requests",
    title=Title("SMB share pending requests"),
    unit=_COUNT,
    color=Color.RED,
)

graph_win_smb_share_latency = Graph(
    name="win_smb_share_latency",
    title=Title("SMB share latency"),
    simple_lines=[
        "win_smb_share_latency_data",
        "win_smb_share_latency_read",
        "win_smb_share_latency_write",
        "win_smb_share_latency_request",
    ],
    minimal_range=MinimalRange(0, 0.01),
    optional=["win_smb_share_latency_request"],
)

graph_win_smb_share_queue = Graph(
    name="win_smb_share_queue",
    title=Title("SMB share queue length"),
    simple_lines=[
        "win_smb_share_queue_avg_data",
        "win_smb_share_queue_avg_read",
        "win_smb_share_queue_avg_write",
        "win_smb_share_queue_current_data",
        "win_smb_share_pending_requests",
    ],
    minimal_range=MinimalRange(0, 1),
    optional=[
        "win_smb_share_queue_avg_read",
        "win_smb_share_queue_avg_write",
        "win_smb_share_queue_current_data",
        "win_smb_share_pending_requests",
    ],
)

metric_win_smb_share_requests_data = Metric(
    name="win_smb_share_requests_data", title=Title("SMB share data requests"), unit=_RATE, color=Color.BLUE
)
metric_win_smb_share_requests_read = Metric(
    name="win_smb_share_requests_read", title=Title("SMB share read requests"), unit=_RATE, color=Color.GREEN
)
metric_win_smb_share_requests_write = Metric(
    name="win_smb_share_requests_write", title=Title("SMB share write requests"), unit=_RATE, color=Color.ORANGE
)
metric_win_smb_share_requests_metadata = Metric(
    name="win_smb_share_requests_metadata", title=Title("SMB share metadata requests"), unit=_RATE, color=Color.PURPLE
)
metric_win_smb_share_throughput_data = Metric(
    name="win_smb_share_throughput_data", title=Title("SMB share throughput"), unit=_BYTES_RATE, color=Color.BLUE
)
metric_win_smb_share_throughput_read = Metric(
    name="win_smb_share_throughput_read", title=Title("SMB share read throughput"), unit=_BYTES_RATE, color=Color.GREEN
)
metric_win_smb_share_throughput_write = Metric(
    name="win_smb_share_throughput_write", title=Title("SMB share write throughput"), unit=_BYTES_RATE, color=Color.ORANGE
)
metric_win_smb_share_open_files = Metric(
    name="win_smb_share_open_files", title=Title("SMB share open files"), unit=_INT, color=Color.BLUE
)
metric_win_smb_share_tree_connects = Metric(
    name="win_smb_share_tree_connects", title=Title("SMB share connections"), unit=_INT, color=Color.GREEN
)

graph_win_smb_share_requests = Graph(
    name="win_smb_share_requests",
    title=Title("SMB share requests"),
    simple_lines=[
        "win_smb_share_requests_data",
        "win_smb_share_requests_read",
        "win_smb_share_requests_write",
        "win_smb_share_requests_metadata",
    ],
    minimal_range=MinimalRange(0, 1),
    optional=["win_smb_share_requests_read", "win_smb_share_requests_write", "win_smb_share_requests_metadata"],
)

graph_win_smb_share_throughput = Graph(
    name="win_smb_share_throughput",
    title=Title("SMB share throughput"),
    simple_lines=[
        "win_smb_share_throughput_data",
        "win_smb_share_throughput_read",
        "win_smb_share_throughput_write",
    ],
    minimal_range=MinimalRange(0, 1024),
    optional=["win_smb_share_throughput_read", "win_smb_share_throughput_write"],
)

graph_win_smb_share_files = Graph(
    name="win_smb_share_files",
    title=Title("SMB share open files and connections"),
    simple_lines=["win_smb_share_open_files", "win_smb_share_tree_connects"],
    minimal_range=MinimalRange(0, 1),
    optional=["win_smb_share_tree_connects"],
)

perfometer_win_smb_share_latency_data = Perfometer(
    name="win_smb_share_latency_data",
    focus_range=FocusRange(Closed(0), Open(0.05)),
    segments=["win_smb_share_latency_data"],
)
