# docker_cpu_normalized

Docker container CPU utilization, normalized to the available CPUs, for Checkmk 2.5.

Author: Marius Gielnik
License: GNU General Public License v2 or later (see LICENSE)
Requires: Checkmk 2.5.0 or newer (the package refuses to install on older versions)

## Problem

`docker stats` and the built-in Docker CPU check report 100 % per fully used CPU
core. A container on a 72-core host can therefore show up to 7200 % and trips
thresholds that are meant for "total CPU in %". On versions older than 2.5.0p12 the
built-in service also reports a bogus "under high load for" duration (Werk 20187)
and can produce negative values after a container restart.

## What this package does

* Adds the service **Docker CPU utilization** for Docker container hosts. It shows the
  utilization in percent of the available CPUs (always 0 to 100 %) and the number of
  CPU cores in use, e.g. `Total CPU: 1.48%, 1.07 of 72 CPUs in use (host CPUs)`.
* Metrics: `util` (normalized, shown in the standard CPU graph) and
  `docker_cpu_cores_used`.
* Levels are configured in the WebUI, *Setup > Services > Service monitoring rules >
  "Docker container CPU utilization (normalized)"*:
  * **Levels over an extended time period** (default): alarm only if the utilization
    stays at or above a threshold (default 90 %) for a given time (default WARN after
    1 h 30 min, CRIT after 3 h), like the built-in CPU check. Short peaks do not alarm.
    The duration is measured with the clock of the check. A period without data for
    more than 30 minutes restarts the measurement.
  * **Levels on normalized CPU utilization**: immediate WARN/CRIT levels (default: off).
* A counter reset (container restart) is detected and ignored instead of producing
  negative values. Repeated data (the Docker plug-in only refreshes every few minutes)
  does not raise an error, the last value is reused.
* The built-in "CPU utilization" service is not changed. Disable it with a rule once
  you rely on the new service.

## Data sources

1. **Standard Docker data (recommended, no agent plug-in):** The check normalizes the
   data that `mk_docker.py` already delivers to the Docker container hosts. Nothing has
   to be rolled out to the Docker hosts. The service is only created on hosts that
   receive the section `docker_container_status`, and only where the discovery rule
   below allows it. The CPU limit of a container is not part of the standard data, the
   value is always related to all CPUs of the Docker host.
2. **Agent plug-in `docker_cpu_normalized` (optional, Linux and Windows):** also reports
   the container CPU limit (`--cpus`, `NanoCpus`, `CpuQuota/CpuPeriod`, `CpuCount`). It
   is deployed with the Agent Bakery. Hosts that receive this data always get the
   service, the discovery rule is not needed. If both sources exist, the data of the
   agent plug-in is used.

## Installation

1. Upload `docker_cpu_normalized-1.2.1.mkp` in *Setup > Maintenance > Extension
   packages*, or on the command line as site user:
   `mkp add docker_cpu_normalized-1.2.1.mkp` and
   `mkp enable docker_cpu_normalized 1.2.1`.
   In a distributed setup install it on the central site.
2. **Standard Docker data:** create the discovery rule *"Docker container CPU
   utilization (normalized)"* (*Setup > Services > Discovery rules*) with
   "Create the service" enabled. Restrict it with a condition, e.g. the host label
   `cmk/docker_object:container` or single host names for a first test. Run a service
   discovery on the container hosts, accept the new service and activate the changes.
   The first value appears after two different data updates from the Docker plug-in
   (up to about 10 minutes with its default 5 minute interval); until then the
   service is pending.
3. **Agent plug-in (optional):** create the Agent Bakery rule *"Docker container CPU
   utilization (normalized)"* for the Docker hosts, bake and roll out the agents.
   Without the Bakery copy `agents/plugins/docker_cpu_normalized` (Linux) or
   `agents/windows/plugins/docker_cpu_normalized.ps1` (Windows) into the plug-in
   directory of the agent. Then run a service discovery.

The discovery rule is off by default on purpose: without a rule no service is created,
so installing the package does not change any host.

## Dependencies of the agent plug-in (monitored host)

* Linux: `docker` CLI, `awk`, `sed`, `sh` (all standard). No `jq`, no Python.
* Windows: `docker.exe` in the PATH of the agent service.
* The agent user must be allowed to talk to Docker (same as for `mk_docker.py`).

Piggyback host names follow the option `container_id` of `docker.cfg` (`short` is the
default, `name`, `long`, `combined`), exactly like `mk_docker.py`, so the data lands on
the same container hosts. Do not use a different `container_id` than `mk_docker.py`,
otherwise new hosts appear.

## Known limitations

* Standard Docker data: the value is the average between two data updates of the
  Docker plug-in; the CPU limit of a container is not taken into account.
* Agent plug-in: the value is a sample of `docker stats --no-stream` taken at agent
  runtime (about one second), not an average over the check interval. The default
  levels over time smooth this; immediate levels react to every peak.
* The Windows plug-in is based on the documented behavior of `docker stats` on
  Windows and has not been tested on a real Windows Docker host.

## Changelog

* 1.2.1: documentation corrected (data sources, installation), LICENSE added.
  No functional changes compared to 1.2.0.
* 1.2.0: the service can be created from the standard Docker data (discovery rule),
  no agent rollout needed.
* 1.1.0: levels over an extended time period (default), immediate levels off by default.
* 1.0.0: first version.
