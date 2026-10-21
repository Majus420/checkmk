# Changelog

## 1.3.1 – 2026-10-21

- Fix: agent plug-in produced no output when the agent exports a TMPDIR that does not exist (Agent Bakery setting, e.g. /var/lib/check_mk_agent/tmp). The plug-in now creates it, falls back to the agent state directory or /tmp, and reports an error line in Repository Health instead of staying silent

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
