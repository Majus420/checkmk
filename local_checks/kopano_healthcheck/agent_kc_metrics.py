#!/usr/bin/env python3
# Author: Marius Gielnik
# Date: 2026-09-29
# Ticket: C_SR-0160293
# Description: Checkmk datasource program. Converts the Prometheus /metrics
#              endpoint of Kopano Cloud (lkb-s-kc01) into local check output.
import json, os, re, sys, time, urllib.request

URL = sys.argv[1]
STATE = os.path.expanduser("~/tmp/agent_kc_metrics.state")
LINE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(.*)\})?\s+(\S+)')
LAB = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')

with urllib.request.urlopen(URL, timeout=20) as r:
    raw = r.read().decode("utf-8", "replace")

m = {}
for l in raw.splitlines():
    if l.startswith("#"):
        continue
    x = LINE.match(l)
    if not x:
        continue
    try:
        v = float(x.group(3))
    except ValueError:
        continue
    m.setdefault(x.group(1), []).append((dict(LAB.findall(x.group(2) or "")), v))

now = time.time()
try:
    old = json.load(open(STATE))
except Exception:
    old = {}
new = {}

def rate(key, v):
    if v is None:
        return None
    new[key] = [now, v]
    o = old.get(key)
    if not o or v < o[1] or now <= o[0]:
        return None
    return (v - o[1]) / (now - o[0])

def val(name, **lab):
    for l, v in m.get(name, []):
        if all(l.get(k) == w for k, w in lab.items()):
            return v
    return None

def san(s):
    return re.sub(r'[^A-Za-z0-9_]', '_', s)

def out(st, name, perf, text):
    p = "|".join("%s=%.6g" % (k, v) for k, v in perf if v is not None) or "-"
    print('%d "%s" %s %s' % (st, name, p, text))

print("<<<local>>>")

up = val("mysql_up")
if up is not None:
    sq = val("mysql_global_status_slow_queries")
    perf = [("threads_connected", val("mysql_global_status_threads_connected")),
            ("uptime", val("mysql_global_status_uptime")),
            ("slow_queries_rate", rate("mysql_slow", sq))]
    out(0 if up == 1 else 2, "Kopano MariaDB", perf, "MariaDB reachable" if up == 1 else "MariaDB DOWN")

up = val("postfix_up")
if up is not None:
    perf = [("queue_" + san(l.get("queue", "x")), v) for l, v in m.get("postfix_size", [])]
    out(0 if up == 1 else 2, "Kopano Postfix", perf, "Postfix reachable" if up == 1 else "Postfix DOWN")

pools = sorted({l["pool"] for l, _ in m.get("phpfpm_accepted_connections", []) if "pool" in l})
for p in pools:
    up = val("phpfpm_up", pool=p)
    perf = [("accepted_rate", rate("fpm_" + p, val("phpfpm_accepted_connections", pool=p))),
            ("active_processes", val("phpfpm_active_processes", pool=p)),
            ("idle_processes", val("phpfpm_idle_processes", pool=p)),
            ("listen_queue", val("phpfpm_listen_queue", pool=p))]
    out(2 if up == 0 else 0, "Kopano PHP-FPM " + p, perf, "PHP-FPM pool " + p)

ap = m.get("apisix_nginx_http_current_connections", [])
if ap:
    perf = []
    for l, v in ap:
        s = san(l.get("state", "x"))
        if s in ("accepted", "handled"):
            perf.append((s + "_rate", rate("apisix_" + s, v)))
        else:
            perf.append((s, v))
    out(0, "Kopano APISIX Connections", perf, "APISIX connections")

cpu = [("cpu_" + san(l.get("e4a", "x")), rate("cpu_" + l.get("e4a", "x"), v)) for l, v in m.get("process_cpu_seconds_total", [])]
if cpu:
    out(0, "Kopano Process CPU", cpu, "CPU usage in cores per process")

mem = [("mem_" + san(l.get("e4a", "x")), v) for l, v in m.get("process_resident_memory_bytes", [])]
if mem:
    out(0, "Kopano Process Memory", mem, "Resident memory per process")

json.dump(new, open(STATE, "w"))