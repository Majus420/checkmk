Docker reports the CPU usage of a container like `docker stats`: **100 % per fully used CPU core**. On a host with many cores a single container can show hundreds or thousands of percent, which breaks every threshold written for "total CPU in %". On Checkmk versions older than 2.5.0p12 the built-in service also shows a bogus "under high load for ... years" duration (Werk 20187).

This package adds the service **Docker CPU utilization** for Docker container hosts. It reports the utilization in percent of the available CPUs (always 0 to 100 %) and the number of CPU cores in use.

## Features

- Normalized CPU utilization per container, e.g. `Total CPU: 1.48%, 1.07 of 72 CPUs in use`
- Metrics `util` (shown in the standard CPU graph) and `docker_cpu_cores_used`
- Levels in the WebUI, with levels over an extended time period as default (WARN after 1 h 30 min, CRIT after 3 h at 90 %), so short peaks do not alarm
- Works with the **standard Docker data** of `mk_docker.py`, no agent plug-in has to be rolled out
- Optional agent plug-in for **Linux and Windows** (Agent Bakery rule) that also reports the container CPU limit
- Counter resets after a container restart are ignored instead of producing negative values
- The built-in "CPU utilization" service is not changed

## Requirements

- Checkmk **2.5.0 or newer**
- Docker hosts monitored with the Docker agent plug-in `mk_docker.py` (container hosts as piggyback hosts)

## Installation

1. Upload the package in *Setup > Maintenance > Extension packages* and enable it.
2. Create the discovery rule *Docker container CPU utilization (normalized)* with "Create the service" enabled, restricted to the container hosts (for example by the host label `cmk/docker_object:container`).
3. Run a service discovery on the container hosts and accept the new service. The first value appears after two data updates of the Docker plug-in (up to about 10 minutes).

No service is created until the discovery rule exists, so installing the package changes no host.

## Notes

- With the standard Docker data the CPU limit of a container is not known, the value is related to all CPUs of the Docker host. The optional agent plug-in also takes the limit into account.
- The Windows agent plug-in has not been tested on a real Windows Docker host.
- Full documentation and changelog are included in the package (`doc` folder).
