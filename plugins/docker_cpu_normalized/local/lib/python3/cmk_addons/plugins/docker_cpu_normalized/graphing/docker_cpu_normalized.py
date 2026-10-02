#!/usr/bin/env python3
# Author: Marius Gielnik
# License: GNU General Public License v2 or later

from cmk.graphing.v1 import Title
from cmk.graphing.v1.metrics import Color, DecimalNotation, Metric, Unit

metric_docker_cpu_cores_used = Metric(
    name="docker_cpu_cores_used",
    title=Title("CPU cores in use"),
    unit=Unit(DecimalNotation("")),
    color=Color.BLUE,
)
