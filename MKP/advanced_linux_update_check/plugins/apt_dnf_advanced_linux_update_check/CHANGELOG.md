# Changelog

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
