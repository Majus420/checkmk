# APT/DNF/Zypper Advanced Linux Update Check

Checkmk extension that monitors pending package updates on **Debian/Ubuntu (apt)**,
**RHEL family/Fedora (dnf, yum)** and **SUSE (zypper)** and rates every update by threat:
an update that fixes an actively exploited vulnerability is reported immediately, an
ordinary security update only after a configurable grace period (e.g. 24 hours, enough
for unattended nightly patching).

- Author: Marius Gielnik
- License: GPL-2.0-or-later
- Checkmk: 2.5.0 or newer (commercial editions for the Agent Bakery rule)
- Package: `apt_dnf_advanced_linux_update_check-1.3.1.mkp` (see [`dist/`](dist/))

## Why

The built-in "APT Updates" check goes WARN the moment a security update is available. It
knows nothing about the age of an update, and its "Interval for checking for updates" is
only the plug-in cache. Hosts that patch themselves at night therefore produce alerts every
day that resolve on their own. Delaying all alerts, on the other hand, also delays the one
update that matters: the fix for a vulnerability that is exploited right now.

## Tiers

Every pending update is put into exactly one tier:

| Tier | Criterion | Default | Can be switched off |
|---|---|---|---|
| zero-day | fixes a CVE in the [CISA KEV catalog](https://www.cisa.gov/known-exploited-vulnerabilities-catalog) | CRIT immediately | yes |
| critical | fixes a CVE with severity critical/high, or an [EPSS](https://www.first.org/epss/) score >= 10 % | WARN after 4 h | yes |
| security | security update (security repository / advisory / patch) | WARN after 24 h | no |
| normal | everything else | OK | no |

Each tier has a delay, a state and an optional escalation (e.g. CRIT after 7 days). The
delay counts from the moment the agent plug-in first saw the package version on the host.
A tier that is switched off falls through to the next one (zero-day → critical → security),
so an actively exploited fix is never reported as less than a security update.

## Services

Services are named after the package manager of the host (`APT`, `DNF`, `YUM` or `Zypper`),
e.g. "APT Pending Updates" on Debian/Ubuntu and "DNF Pending Updates" on RHEL.

| Service | Content |
|---|---|
| \<PM\> Pending Updates | tiers above, per-package details (version, age, severity, advisory/patch, CVEs, "actively exploited"), apt: updates only installable via dist-upgrade, removals, phased updates; held/locked packages; ignore list |
| \<PM\> Reboot Required | reboot-required flag, dnf/yum needs-restarting, zypper needs-rebooting, newer kernel installed than running, missing modules; optional escalation by age; services needing a restart |
| \<PM\> Repository Health | metadata age and refresh errors, security information available (security repository / advisory metadata / patch metadata), apt: repositories of a different release, duplicate sources, legacy keyring; package database problems; autoremovable and orphaned packages; automatic updates (unattended-upgrades, dnf-automatic, yum-cron); OS end of life; time since last package change; threat data age |

Additionally:

- **HW/SW inventory** (`Software > Applications > Linux updates`): pending updates and a CVE
  table (CVE, package, actively exploited, severity, EPSS, installed / fixed version) - answers
  "which hosts are affected by CVE-…" and "where is package X still unpatched" in the
  inventory views. Requires the HW/SW inventory to be enabled for the hosts.
- **Host labels** (set automatically by discovery, only stable values):
  `linux_updates/package_manager` (apt/dnf/yum/zypper), `linux_updates/auto_updates`
  (enabled/disabled/not_installed), `linux_updates/security_info` (yes/no),
  `linux_updates/livepatch` (canonical/kernel) - usable in rule conditions, views and
  notifications.
- **Graphs and perfometers**: pending updates by tier (stacked), age of the oldest security
  update, reboot pending since, metadata age.
- **Kernel livepatch** (Canonical Livepatch, kpatch, SUSE klp via `/sys/kernel/livepatch`):
  shown in Reboot Required; optional own state if only a newer kernel is pending and a
  livepatch is active.
- **snap / flatpak**: pending updates as info (own state), collected together with the
  metadata refresh because they query the stores online.

All states and levels are configurable in the rules "APT/DNF/Zypper: pending updates",
"APT/DNF/Zypper: reboot required" and "APT/DNF/Zypper: repository health" (Setup > Services >
Service monitoring rules > Operating System Resources, search for "apt").

## Package managers

| Package manager | Distributions | Pending updates | Security / severity / CVEs |
|---|---|---|---|
| apt | Debian, Ubuntu | simulated `apt-get upgrade` AND `apt-get dist-upgrade` | security repository; CVEs + severity from [OSV](https://osv.dev) by version comparison |
| dnf 4/5 | RHEL, Rocky, Alma, Oracle Linux, Fedora, CentOS Stream | `dnf repoquery --upgrades` | distribution advisories (`updateinfo` / `advisory`) |
| yum | EL7 | `yum check-update` | `yum updateinfo` |
| zypper | SLES, openSUSE | `zypper list-updates` | security patches (category, severity, CVEs), package-to-patch mapping |

Severities are normalized: important = high, moderate = medium. KEV and EPSS apply to all
distributions via the CVE ids. Nothing is ever installed; all queries use the local package
cache only.

## Components

| Component | Site path | Purpose |
|---|---|---|
| agent plug-in | `local/share/check_mk/agents/plugins/linux_updates` | POSIX sh, no Python needed on the host |
| bakery plug-in | `local/lib/python3/cmk/base/cee/plugins/bakery/linux_updates.py` | deploys plug-in + `/etc/check_mk/linux_updates.cfg` |
| check plug-ins | `local/lib/python3/cmk_addons/plugins/linux_updates/agent_based/` | section + 3 services |
| rule sets | `local/lib/python3/cmk_addons/plugins/linux_updates/rulesets/` | 3 check rules + bakery rule |
| helpers | `local/lib/python3/cmk_addons/plugins/linux_updates/lib/common.py` | dpkg version comparison, threat/EOL data |
| threat data updater | `local/bin/linux_updates_threatdb` | downloads KEV, EPSS, OSV, end-of-life data |
| man pages | `local/lib/python3/cmk_addons/plugins/linux_updates/checkman/` | check documentation |

## Installation

1. Upload the MKP (Setup > Maintenance > Extension packages) or `mkp add` + `mkp enable` as site user.
2. Create the Agent Bakery rule "APT/DNF/Zypper: Linux update check (agent plug-in)"
   (Setup > Agents > Windows, Linux, Solaris, AIX > Agent rules), bake and deploy the agents.
3. Run service discovery on the hosts.

Replacing the built-in APT check: set the bakery rule "APT normal and security updates
(Linux)" to "Do not deploy" and remove the vanished "APT Updates" services.

## Agent Bakery rule

| Option | Default |
|---|---|
| Deployment type | asynchronous (cached), interval 1 h, minimum 5 min; or do not deploy. The plug-in never runs synchronously, so a slow metadata refresh can never block the agent |
| Refresh package metadata | yes, respecting the minimum interval |
| Minimum interval between metadata refreshes | 4 h (at least 1 h, enforced in rule, bakery and plug-in) |
| Timeout for the metadata refresh | 300 s |

The refresh (`apt-get update`, `dnf makecache`, `yum makecache fast`, `zypper refresh`) is
the only step that contacts the mirrors. It runs only when both the plug-in's last attempt
and the last refresh by anybody (e.g. `apt-daily.timer`) are older than the minimum interval,
so a failing mirror is never hammered.

Host-side state: `/var/lib/check_mk_agent/linux_updates.seen` (first-seen times),
`linux_updates.refresh` and `linux_updates.refresh.log` (last refresh).

## Threat and end-of-life data

`linux_updates_threatdb` writes to `~/var/check_mk/linux_updates/threatdb/` on each site. No
cron or manual setup is needed: the check plug-ins start it automatically in the background
as soon as the data is missing or older than 6 hours (at most one attempt per hour, a lock
prevents parallel runs), so every site that monitors Linux hosts - including new remote
sites - keeps its own data current. The first run takes a few minutes. Manual run:
`linux_updates_threatdb`, status: `linux_updates_threatdb --status`.

| File | Content | Source |
|---|---|---|
| `cves.json` | KEV list + EPSS scores >= 1 % | CISA KEV, FIRST EPSS |
| `debian_<version>.json`, `ubuntu_<version>.json` | CVE → fixed version per source package | OSV |
| `eol.json` | end-of-life date per distribution release | [endoflife.date](https://endoflife.date) |
| `meta.json` | status per source | – |

Proxy: sites without direct internet access use the environment variables (`HTTPS_PROXY`,
e.g. in `~/etc/environment`) or `~/etc/linux_updates_threatdb.conf` with `proxy = http://host:port`.

Network access (site, HTTPS): `www.cisa.gov`, `epss.empiricalsecurity.com`,
`osv-vulnerabilities.storage.googleapis.com`, `endoflife.date`. Downloads are conditional
(ETag/Last-Modified); a failed download keeps the last good copy. Log:
`~/var/log/linux_updates_threatdb.log`. Without threat data the zero-day/critical tiers fall
back to security/normal and the Repository Health service reports the missing data; nothing is
silently dropped.

## Testing

```
cmk -d <host> | sed -n '/<<<linux_updates/,/<<<[^l]/p' | head -20
cmk -nv --detect-plugins=linux_updates_pending,linux_updates_reboot,linux_updates_repos <host>
cmk-validate-plugins 2>&1 | grep -i linux_updates
linux_updates_threatdb --status
```

Tested before release:

- apt: Ubuntu 24.04 with the real apt (security, normal, phased, repository errors, first-seen, minimum interval)
- dnf 4.14 and zypper 1.14: real binaries against a test repository with security advisories/patches (CVEs, severity, multi-package patch, lock)
- dpkg version comparison against `dpkg --compare-versions`: 1941 comparisons, 0 differences
- all three checks on all three package managers, switching off tiers, escalation, end of life
- rule sets against the Checkmk 2.5.0 plug-in APIs; MKP built with cmk-mkp-tool 3.0.0

Not yet verified on real hosts: dnf5 (Fedora 41+, RHEL 10), yum (EL7).

## Known limitations

- If the agent exports a TMPDIR that does not exist, the plug-in creates it (or falls back to the agent state directory / /tmp).

- Age counts from first sight on the host, not from publication (apt provides no dates).
- apt: severity only where OSV provides it; KEV and EPSS apply regardless.
- zypper: packages not contained in any patch count as normal.
- Ubuntu 22.04 (apt 2.4) reports phased updates as "kept back".
- Ubuntu Pro/ESM fixes are not rated.
- Repositories without security metadata (e.g. CentOS Stream) cannot provide security classification; the Repository Health service reports this.

## Building the package

On a Checkmk **test** site, as site user, from this directory:

```
./build_mkp.sh
```

The script copies `local/` into the site, creates the manifest with `mkp template`, sets
the package fields and runs `mkp package`. The result is in `~/var/check_mk/packages_local/`.

## Removal

1. Set the bakery rule to "Do not deploy", bake and deploy the agents.
2. Remove the services via service discovery.
3. Remove the extension package.
4. On every site: `rm -r ~/var/check_mk/linux_updates`.

## License

GPL-2.0-or-later, see [LICENSE](LICENSE). The Checkmk plug-in APIs are licensed under GPL v2.
