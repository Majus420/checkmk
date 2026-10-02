#!/bin/bash
# Author: Marius Gielnik
# Date: 2026-10-01
# Ticket: C_SR-0160293
# Description: Writes Kopano Cloud metrics as piggyback data for host LKB-S-KC01.
D=/omd/sites/extern/tmp/check_mk/piggyback/LKB-S-KC01
SD=/omd/sites/extern/tmp/check_mk/piggyback_sources
mkdir -p "$D" "$SD"
T=$(mktemp /omd/sites/extern/tmp/kc_pb.XXXXXX) || exit 1
/omd/sites/extern/var/kc/agent_kc_metrics http://192.168.119.50:9100/metrics > "$T" 2>/dev/null
[ "$(grep -c '^[0-9] "Kopano' "$T")" -ge 1 ] || { rm -f "$T"; exit 1; }
chmod 600 "$T"; mv "$T" "$D/KOPANO-METRICS"; touch "$SD/KOPANO-METRICS"