# Changelog

## 1.3.3 – 2026-11-11

- Fix: "package database problems" was reported while another package operation was running (unattended-upgrades, Ansible, manual apt) and always on agents running as non-root. `apt-get check` needs the dpkg lock and failed on it; it now runs without locking (`Debug::NoLocking`), like the simulated upgrade. Real dependency problems are still detected
- Repository Health: a failed or timed-out metadata refresh is only reported if there was no successful refresh within a grace period (new parameter, default 24 h, 0 = report every failure). A single slow refresh no longer causes a warning; a refresh that keeps failing still does
- Errors from the plug-in's own metadata refresh (e.g. a mirror that could not be reached once) follow the same grace period and are shown with the refresh status, instead of a separate immediate "package manager errors" warning. Errors that keep coming back are still reported. Warnings of the refresh (duplicate sources, legacy keyring) are unchanged
- Tested against: dpkg lock held by another process, non-root agent, real unmet dependency (still reported), failure with recent / old / no successful refresh, refresh errors within and after the grace period, old agent output, dash and bash

## 1.3.2 – 2026-11-10

- Fix: Repository Health stayed WARN with "last refresh failed/timeout" although the package metadata were refreshed successfully afterwards (e.g. by apt-daily.timer). A failed or timed-out refresh of the plug-in is now only reported until a successful refresh follows. Success is taken only from markers written on success (own refresh, apt `update-stamp`, `update-success-stamp`), not from `lists/partial`, which a failed run touches too. Older agent plug-ins keep the previous behaviour

## 1.3.1 – 2026-10-21

- Fix: agent plug-in produced no output when the agent exports a TMPDIR that does not exist (Agent Bakery setting, e.g. /var/lib/check_mk_agent/tmp). The plug-in now creates it, falls back to the agent state directory or /tmp, and reports an error line in Repository Health instead of staying silent
- Fix: agent plug-in aborted without output when the agent state directory is not writable (agent running as non-root user, read-only or foreign MK_VARDIR). State now falls back to /var/tmp/linux_updates.<uid>; without any writable state the plug-in still reports and warns that first-seen times are not kept
- Non-root agent: the metadata refresh is skipped (shown as notice in Repository Health) instead of failing on every run
- A corrupted snap/flatpak cache file can no longer inject data into the agent output
- An interrupted run (SIGTERM/SIGINT/SIGHUP) now exits non-zero, so the agent keeps the last complete result instead of a partial one
- Tested against: missing / non-writable / file-type TMPDIR, read-only and missing state directory, non-root agent, umask 077, minimal PATH, empty environment, closed stdin, CRLF and invalid config values, corrupted state files, dash and bash

## 1.3.0 – 2026-10-21

- HW/SW inventory: pending updates and CVE table (searchable by CVE / package)
- Automatic host labels: package manager, automatic updates, security information, livepatch
- Graphs and perfometers for all metrics
- Kernel livepatch detection (Canonical Livepatch, kpatch, SUSE klp) with optional state for "only kernel pending, livepatch active"
- snap / flatpak pending updates (cached, together with the metadata refresh)
- Proxy setting for the threat data updater (`~/etc/linux_updates_threatdb.conf` or HTTPS_PROXY)

## 1.2.1 – 2026-10-21

- Bakery rule: option "run synchronously" removed, the plug-in always runs asynchronously (cached). Existing rules with "synchronous" are migrated to asynchronous, 1 hour

## 1.2.0 – 2026-10-21

- Threat data is refreshed automatically: the check plug-ins start `linux_updates_threatdb` in the background when the data is older than 6 hours. No cron and no manual setup per site; `--install-cron` removed

## 1.1.0 – 2026-10-21

- Services are named after the package manager: "APT/DNF/YUM/Zypper Pending Updates", "... Reboot Required", "... Repository Health" (item = package manager); rules can be restricted per package manager

## 1.0.0 – 2026-10-21

First release.

- Agent plug-in for apt (Debian/Ubuntu), dnf 4/5 and yum (RHEL family, Fedora) and zypper (SUSE)
- apt: simulated upgrade AND dist-upgrade, kept back, new and removed packages, phased updates
- dnf/yum: security, severity, advisory ids and CVEs from the distribution advisories
- zypper: security, severity and CVEs from security patches, package-to-patch mapping
- First-seen time per package version on the host
- Tiers zero-day (CISA KEV), critical (severity, EPSS), security, normal with delay, state and escalation; zero-day and critical can be switched off
- Services "Linux Pending Updates", "Linux Reboot Required", "Linux Repository Health"
- Metadata refresh with enforced minimum interval
- Threat and end-of-life data updater (CISA KEV, EPSS, OSV, endoflife.date) with site cron
- Agent Bakery rule with synchronous/asynchronous deployment
