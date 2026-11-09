# Windows SMB Share Performance (Checkmk MKP)

Monitors SMB shares on Windows file servers **per share**: latency and queue length,
based on the Windows performance object **"SMB Server Shares"**.

- **Author:** Marius Gielnik
- **License:** GPL-2.0-or-later
- **Checkmk:** 2.5.0 or newer (Agent Bakery rule needs a commercial edition)
- **Windows:** Server 2012 or newer, Windows PowerShell 2.0 or newer

## What you get

Service `SMB Share <name>` per share with:

| Value | Windows counter | Metric |
|---|---|---|
| Data latency | Avg. sec/Data Request | `win_smb_share_latency_data` |
| Read latency | Avg. sec/Read | `win_smb_share_latency_read` |
| Write latency | Avg. sec/Write | `win_smb_share_latency_write` |
| Request latency (all requests) | Avg. sec/Request | `win_smb_share_latency_request` |
| Avg. data / read / write queue length | Avg. Data/Read/Write Queue Length | `win_smb_share_queue_avg_*` |
| Current data queue length | Current Data Queue Length | `win_smb_share_queue_current_data` |
| Pending requests | Current Pending Requests | `win_smb_share_pending_requests` |
| Data / read / write / metadata requests | Data/Read/Write/Metadata Requests/sec | `win_smb_share_requests_*` |
| Throughput / read / write | Data/Read/Write Bytes/sec | `win_smb_share_throughput_*` |
| Open files | Current Open File Count | `win_smb_share_open_files` |
| Connections | Tree Connect Count | `win_smb_share_tree_connects` |

An interval without any request shows "no requests" instead of a latency of 0 seconds, so an
idle share cannot be mistaken for a fast one.

Graphs "SMB share latency", "SMB share queue length", "SMB share requests", "SMB share throughput"
and "SMB share open files and connections", perfometer on data latency.

## How it works

- The agent plug-in `win_smb_shares.ps1` reads the **raw** counters through the .NET
  performance counter classes - the same data perfmon and Get-Counter show - using the English
  counter names, which .NET also resolves on German or other localized Windows.
- WMI (`Win32_PerfRawData_Counters_SMBServerShares`) is only a fallback: on some servers this
  class does not follow the real traffic (0 requests in WMI while perfmon showed traffic). The
  source in use is shown in the service details.
- The plug-in also sends the **counter type** of every value. The Checkmk server computes
  latency and queue length from two consecutive agent outputs according to that type
  (PERF_AVERAGE_TIMER, *_QUEUELEN_TYPE, RAWCOUNT ...). Unknown counter types are never guessed.
- Values are averages over the check interval.
- First check after discovery: "Initializing counters". Counter resets (reboot) start over
  cleanly, cached agent output reuses the last values.
- No counter source readable: the service goes UNKNOWN with the error message of the plug-in.
- The local path of every share is read from `Win32_Share` and shown in the service details.

## Installation

1. Upload the MKP: *Setup > Maintenance > Extension packages > Upload package*.
2. Agent rule *Setup > Agents > Windows, Linux, Solaris, AIX > Agent rules >*
   **Windows: SMB share performance (agent plug-in)** — synchronous recommended
   (values are averages between two agent runs). Bake and deploy the agents.
   Without the Bakery: copy `win_smb_shares.ps1` to `C:\ProgramData\checkmk\agent\plugins\`.
3. Run the service discovery on the file server.

## Rules

| Rule | Where | Purpose |
|---|---|---|
| Windows: SMB share performance (agent plug-in) | Agent rules | deploy plug-in, synchronous / asynchronous / do not deploy, timeout |
| Windows SMB share discovery | Discovery rules | include / exclude shares by regular expression |
| Windows SMB share performance | Service monitoring rules (Storage) | upper levels per value, per share (item) |

**Select shares by local path (easiest):** in the discovery rule enter the folders as plain
text, e.g. `E:\home`, `D:\Shares\Public`, or `E:\*` for all shares below a folder. No need to know
the share names (hidden shares end in `$`). Case and a trailing backslash do not matter. The local
path is also shown in the details of every service.

**Discovery default:** all shares except the administrative shares Windows creates itself
(`^[A-Za-z]\$$`, `^(ADMIN|IPC|print)\$$`) and `^_Total$`. Hidden user shares such as `home$`
are discovered. The share name is used without the leading `\\*\`.

**Levels default (no rule needed):**

| Value | WARN | CRIT |
|---|---|---|
| Data / read / write latency | 20 ms | 50 ms |
| Avg. data queue length | 2 | 5 |
| Current data queue length | 2 | 5 |

Request latency (incl. metadata), read/write queue, pending requests, requests/s, throughput,
open files and connections are recorded without levels by default (open files and connections
can get levels in the rule). 20 ms and a queue of 2 are Microsoft's rules of thumb for the disk counters
(Avg. Disk sec/Read/Write, Current Disk Queue Length) that the SMB share counters were modelled
after; the CRIT values are the author's choice. Adjust per share with the rule, "No levels"
switches a default off.

## Test on the Windows host

    powershell -NoProfile -ExecutionPolicy Bypass -File "C:\ProgramData\checkmk\agent\plugins\win_smb_shares.ps1"

Expected: `<<<win_smb_shares:sep(9)>>>`, a `[types]` line and one line per share.

## Files

| Path | Purpose |
|---|---|
| `local/share/check_mk/agents/windows/plugins/win_smb_shares.ps1` | agent plug-in |
| `local/lib/python3/cmk_addons/plugins/win_smb_shares/agent_based/win_smb_shares.py` | parser, discovery, check |
| `local/lib/python3/cmk_addons/plugins/win_smb_shares/rulesets/win_smb_shares_checks.py` | check + discovery rule |
| `local/lib/python3/cmk_addons/plugins/win_smb_shares/rulesets/win_smb_shares_bakery.py` | Agent Bakery rule |
| `local/lib/python3/cmk/base/cee/plugins/bakery/win_smb_shares.py` | Agent Bakery plug-in |
| `local/lib/python3/cmk_addons/plugins/win_smb_shares/graphing/win_smb_shares.py` | metrics, graphs, perfometer |
| `local/lib/python3/cmk_addons/plugins/win_smb_shares/checkman/win_smb_shares` | man page |

## Build

    python3 build_mkp.py

Creates `dist/windows_smb_share_performance-<version>.mkp` (format of cmk-mkp-tool 3.0.0,
no Checkmk site needed). Increase `VERSION` in `build_mkp.py` with every change.

## Uninstall

Remove the discovery/levels rules and services, set the agent rule to "Do not deploy" (bake and
deploy), then remove the package under *Setup > Maintenance > Extension packages*.
