# Changelog - windows_smb_share_performance

## 1.4.1 - 2026-11-10
- Share name filters (default exclusions and the discovery rule's regular expressions) are
  case insensitive, like share names on Windows (ADMIN$ = admin$, home$ = HOME$).

## 1.4.0 - 2026-11-09
- New values per share: data/read/write/metadata requests per second, throughput
  (data/read/write bytes per second), open files, connections (tree connects).
- An interval without any request shows "no requests" instead of a latency of 0 seconds.
- Optional levels for open files and connections; new graphs "SMB share requests",
  "SMB share throughput", "SMB share open files and connections".

## 1.3.0 - 2026-11-09
- Agent plug-in reads the counters via .NET performance counters (same data as perfmon /
  Get-Counter) with the English counter names, which also works on localized Windows.
  Found on a production file server: the WMI class Win32_PerfRawData_Counters_SMBServerShares
  reported 0 requests while perfmon showed 1.6 requests/s and 13.8 ms latency on the same share.
- WMI stays as fallback only; the source in use is reported by the plug-in and shown in the
  service details.

## 1.2.0 - 2026-11-09
- Agent plug-in also sends the local path of every share (Win32_Share, language independent).
- Service details show the local path ("Path: E:\home").
- Discovery rule: new option "Only discover shares with these local paths" - plain paths
  instead of share names or regular expressions (E:\home, D:\Shares\Public; E:\* for all
  shares below a folder; case and trailing backslash do not matter).

## 1.1.0 - 2026-11-09
- Default levels without any rule: data/read/write latency 20/50 ms, average and current
  data queue length 2/5. 20 ms and a queue of 2 follow Microsoft's rules of thumb for the
  disk counters the SMB share counters were modelled after; CRIT values are the author's choice.
  "No levels" in the rule switches a default off.
- Rule form prefill for current data queue length aligned to 2/5.

## 1.0.1 - 2026-11-09
- Default discovery filter now only excludes the administrative shares Windows creates
  itself (drive shares like C$, ADMIN$, IPC$, print$) and _Total. Hidden user shares
  such as home$ are discovered without an extra rule (found on the first real file server).

## 1.0.0 - 2026-11-09
- First release: agent plug-in win_smb_shares.ps1 (WMI raw counters "SMB Server Shares"),
  check plug-in "SMB Share <name>", check and discovery rules, Agent Bakery rule, graphs, perfometer.
