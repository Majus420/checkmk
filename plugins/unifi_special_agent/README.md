# unifi_special_agent

CheckMK Special Agent for monitoring Unifi Controllers.

## Description

Monitors Unifi Controller instances via the Unifi API. Provides checks for connected devices, access points, switches, and more.

## Changes vs. original

This is a fork of the original [Unifi special-agent check](https://gitlab.com/checkmk-extensions/plugins/unifi) by Frank Baier, released under the Apache 2.0 license.

**Fix:** Removed the `Version: 1.0` output from the agent which caused a false `WARN` state on the `Check_MK` service in CheckMK 2.2.x.

## Requirements

- CheckMK ≥ 2.2.0
- Unifi Controller ≥ 6.0

## Installation

Download the latest `.mkp` from the [releases](https://github.com/Majus420/checkmk/releases) and install via:

```bash
mkp install unifi_special_agent-1.0.mkp
```

Or via the CheckMK GUI: **Setup → Extension packages → Upload package**

## Configuration

Configure the special agent in CheckMK under:

**Setup → Other integrations → Unifi Controller**

Set the Unifi Controller hostname/IP, port, and credentials.

## Changelog

### 1.0
- Fork of original version 2.2.1 by Frank Baier
- Fixed: `Version: 1.0` removed from agent output (caused false WARN on Check_MK service)

## License

Apache License 2.0 — see [LICENSE](./LICENSE)

Original work by Frank Baier <dev@baier-nt.de>  
Fork maintained by Marius Gielnik <marius.gielnik@comramo.de>
