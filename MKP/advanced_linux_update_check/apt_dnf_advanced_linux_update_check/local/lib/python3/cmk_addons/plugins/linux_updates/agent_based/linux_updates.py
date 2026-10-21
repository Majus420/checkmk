#!/usr/bin/env python3
"""
linux_updates - check plug-ins for package updates on Linux
                (Debian/Ubuntu apt, RHEL family/Fedora dnf + yum, SUSE zypper)

Author:   Marius Gielnik
Project:  https://github.com/Majus420/checkmk/tree/main/MKP/advanced_linux_update_check
Version:  1.3.1
License:  GPL-2.0-or-later

Section:  linux_updates (agent plug-in "linux_updates", deployed by the bakery
          rule "APT/DNF/Zypper: Linux update check (agent plug-in)")

Services (named after the package manager: APT, DNF, YUM or Zypper):
  <PM> Pending Updates     every pending update is put into one tier:
                              zero-day - fixes a CVE in the CISA KEV catalog
                              critical - fixes a CVE with high severity or
                                         an EPSS score above threshold
                              security - security update (security repository,
                                         security advisory or security patch)
                              normal   - everything else
                            zero-day and critical can be switched off; each
                            tier has its own delay (time since the update was
                            first seen on the host), state and escalation.
                            Rule: "APT/DNF/Zypper: pending updates"
  <PM> Reboot Required      reboot flag / needs-restarting / zypper
                            needs-rebooting, newer kernel, missing modules,
                            services to restart. Rule: "APT/DNF/Zypper: reboot required"
  <PM> Repository Health    metadata age, refresh errors, security information
                            available, foreign suites (apt), keyring (apt),
                            package database, autoremove, orphaned packages,
                            automatic updates, OS end of life, last upgrade,
                            threat data age. Rule: "APT/DNF/Zypper: repository health"

CVE sources:  dnf/yum/zypper: CVEs from the distribution's advisories (agent)
              apt: CVEs from OSV via the threat data (version comparison)
Threat data:  ~/var/check_mk/linux_updates/threatdb (written by
              ~/local/bin/linux_updates_threatdb; started automatically by
              this check in the background when the data is older than 6 h)
Test:         cmk -nv --detect-plugins=linux_updates_pending,linux_updates_reboot,linux_updates_repos <host>
"""

from __future__ import annotations

import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from cmk.agent_based.v2 import (
    AgentSection,
    Attributes,
    CheckPlugin,
    CheckResult,
    DiscoveryResult,
    HostLabel,
    HostLabelGenerator,
    InventoryPlugin,
    InventoryResult,
    Metric,
    Result,
    Service,
    State,
    StringTable,
    TableRow,
    check_levels,
    render,
)

from cmk_addons.plugins.linux_updates.lib.common import (
    ecosystem_from_host,
    ensure_threatdb_fresh,
    fixed_cves,
    load_cve_info,
    load_ecosystem,
    load_meta,
    lookup_eol,
    normalize_severity,
)

# ================================================================== section


@dataclass(frozen=True)
class Update:
    kind: str  # up | dist | new
    package: str
    source: str
    installed: str
    candidate: str
    security: bool
    first_seen: float
    origin: str
    severity: str
    advisories: str
    cves: tuple[str, ...]


@dataclass(frozen=True)
class Repo:
    priority: str
    location: str
    origin: str
    archive: str
    codename: str
    label: str
    component: str


@dataclass
class Section:
    plugin_version: str = ""
    agent_time: float = 0.0
    os_id: str = ""
    os_version: str = ""
    os_codename: str = ""
    arch: str = ""
    backend: str = ""
    container: str = "none"
    refresh_mode: str = "never"
    cache_ts: float = 0.0
    refresh_ts: float = 0.0
    refresh_status: str = "never"
    updates: list[Update] = field(default_factory=list)
    removals: list[tuple[str, str]] = field(default_factory=list)
    withheld: list[tuple[str, str]] = field(default_factory=list)
    held: list[str] = field(default_factory=list)
    autoremove: list[str] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    messages: list[tuple[str, str]] = field(default_factory=list)
    repos: list[Repo] = field(default_factory=list)
    secinfo: bool | None = None
    secinfo_detail: str = ""
    legacy_keyring: bool = False
    audit_count: int = 0
    audit_detail: str = ""
    auto_name: str = ""
    auto_installed: bool = False
    auto_enabled: bool = False
    auto_last_run: float = 0.0
    auto_errors: int = 0
    last_upgrade: float = 0.0
    reboot: list[tuple[str, float, str]] = field(default_factory=list)
    restart: list[str] = field(default_factory=list)
    eol_host: str = ""
    livepatch_source: str = ""
    livepatch_state: str = ""
    livepatch_modules: str = ""
    apps: list[tuple[str, str, str]] = field(default_factory=list)  # (kind, name, version)


def _f(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return 0.0


def _i(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


def parse_linux_updates(string_table: StringTable) -> Section | None:
    if not string_table:
        return None
    s = Section()
    for row in string_table:
        if not row:
            continue
        key, rest = row[0], row[1:]
        if len(rest) < 11:
            rest = rest + [""] * (11 - len(rest))
        if key == "meta":
            s.plugin_version, s.agent_time = rest[0], _f(rest[1])
        elif key == "os":
            s.os_id, s.os_version, s.os_codename, s.arch = rest[0], rest[1], rest[2], rest[3]
        elif key == "backend":
            s.backend = rest[0]
        elif key == "container":
            s.container = rest[0] or "none"
        elif key == "cfg":
            s.refresh_mode = rest[0]
        elif key == "cache":
            s.cache_ts = _f(rest[0])
        elif key == "refresh":
            s.refresh_ts, s.refresh_status = _f(rest[0]), rest[1]
        elif key == "upd":
            s.updates.append(
                Update(
                    kind=rest[0],
                    package=rest[1],
                    source=rest[2] or rest[1],
                    installed=rest[3],
                    candidate=rest[4],
                    security=rest[5] == "1",
                    first_seen=_f(rest[6]),
                    origin=rest[7],
                    severity=normalize_severity(rest[8]),
                    advisories=rest[9],
                    cves=tuple(c for c in rest[10].split(",") if c.startswith("CVE-")),
                )
            )
        elif key == "rem":
            s.removals.append((rest[0], rest[1]))
        elif key == "withheld":
            s.withheld.append((rest[0], rest[1]))
        elif key == "hold":
            s.held.append(rest[0])
        elif key == "autoremove":
            s.autoremove.append(rest[0])
        elif key == "orphan":
            s.orphans.append(rest[0])
        elif key == "msg":
            s.messages.append((rest[0], "|".join(x for x in rest[1:] if x)))
        elif key == "repo":
            s.repos.append(Repo(*rest[:7]))
        elif key == "secinfo":
            s.secinfo, s.secinfo_detail = rest[0] == "1", rest[1]
        elif key == "legacykey":
            s.legacy_keyring = rest[0] == "1"
        elif key == "audit":
            s.audit_count, s.audit_detail = _i(rest[0]), rest[1]
        elif key == "auto":
            s.auto_name = rest[0]
            s.auto_installed = rest[1] == "1"
            s.auto_enabled = rest[2] == "1"
            s.auto_last_run = _f(rest[3])
            s.auto_errors = _i(rest[4])
        elif key == "lastupgrade":
            s.last_upgrade = _f(rest[0])
        elif key == "reboot":
            s.reboot.append((rest[0], _f(rest[1]), rest[2]))
        elif key == "restart":
            s.restart.append(rest[0])
        elif key == "eol":
            s.eol_host = rest[1]
        elif key == "livepatch":
            s.livepatch_source, s.livepatch_state, s.livepatch_modules = rest[0], rest[1], rest[2]
        elif key in ("snap", "flatpak"):
            s.apps.append((key, rest[0], rest[1]))
    return s


def host_labels_linux_updates(section: Section) -> HostLabelGenerator:
    """Stable host labels only - values that change daily (reboot required,
    pending updates) would trigger "new host labels" on every discovery."""
    if section.backend:
        yield HostLabel("linux_updates/package_manager", section.backend)
    if section.auto_name not in ("", "-"):
        if section.auto_installed and section.auto_enabled:
            auto = "enabled"
        elif section.auto_installed:
            auto = "disabled"
        else:
            auto = "not_installed"
        yield HostLabel("linux_updates/auto_updates", auto)
    if section.backend == "apt":
        has_sec = any(
            r.archive.endswith("-security") or r.codename.endswith("-security") or "security" in r.label.lower()
            for r in section.repos
        )
        if section.repos:
            yield HostLabel("linux_updates/security_info", "yes" if has_sec else "no")
    elif section.secinfo is not None:
        yield HostLabel("linux_updates/security_info", "yes" if section.secinfo else "no")
    if section.livepatch_source:
        yield HostLabel("linux_updates/livepatch", section.livepatch_source)


agent_section_linux_updates = AgentSection(
    name="linux_updates",
    parse_function=parse_linux_updates,
    host_label_function=host_labels_linux_updates,
)


BACKEND_LABELS = {"apt": "APT", "dnf": "DNF", "yum": "YUM", "zypper": "Zypper"}


def discover_linux_updates(section: Section) -> DiscoveryResult:
    yield Service(item=BACKEND_LABELS.get(section.backend, section.backend.upper() or "Package"))


def _state(value: Any, default: int = 0) -> State:
    try:
        return State(int(value))
    except (TypeError, ValueError):
        return State(default)


def _age(now: float, ts: float) -> float:
    return max(0.0, now - ts) if ts > 0 else 0.0


# ========================================================= pending updates

TIERS = ("zero_day", "critical", "security", "normal")
TIER_TITLES = {"zero_day": "zero-day", "critical": "critical", "security": "security", "normal": "normal"}

DEFAULT_PENDING: dict[str, Any] = {
    "tier_zero_day": ("enabled", {"state": 2, "delay": 0.0}),
    "tier_critical": ("enabled", {"state": 1, "delay": 14400.0}),
    "tier_security": {"state": 1, "delay": 86400.0},
    "tier_normal": {"state": 0, "delay": 0.0},
    "critical_severities": ["critical", "high"],
    "epss_threshold": 10.0,
    "removals_state": 0,
    "held_state": 0,
    "withheld_state": 0,
    "apps_state": 0,
}


def _tier_config(params: Mapping[str, Any], tier: str) -> Mapping[str, Any] | None:
    """Tier settings, None if the tier is switched off"""
    value = params.get(f"tier_{tier}", DEFAULT_PENDING[f"tier_{tier}"])
    if isinstance(value, tuple):
        mode, cfg = value
        return cfg if mode == "enabled" and isinstance(cfg, Mapping) else None
    return value if isinstance(value, Mapping) else None


def _tier_state(cfg: Mapping[str, Any], age: float) -> State:
    state = State.OK
    if age >= float(cfg.get("delay", 0.0)):
        state = _state(cfg.get("state", 0))
    esc = cfg.get("escalate")
    if esc and age >= float(esc.get("after", 0.0)):
        state = State.worst(state, _state(esc.get("state", 2)))
    return state


@dataclass
class Cve:
    cve: str
    kev: bool
    severity: str
    epss: float


@dataclass
class Rated:
    update: Update
    tier: str
    age: float
    cves: list[Cve]
    state: State


def _cves_for(
    upd: Update,
    db: Mapping[str, list[list[Any]]] | None,
    kev: frozenset[str],
    epss: Mapping[str, float],
) -> list[Cve]:
    found: dict[str, Cve] = {}
    # CVEs named by the distribution's advisory (dnf/yum/zypper)
    for cve in upd.cves:
        found[cve] = Cve(cve, cve in kev, upd.severity, epss.get(cve, 0.0))
    # CVEs fixed between installed and candidate version (apt via OSV)
    if db:
        for cve, is_kev, sev, score in fixed_cves(db, upd.source, upd.installed, upd.candidate):
            prev = found.get(cve)
            found[cve] = Cve(
                cve,
                is_kev or cve in kev or (prev.kev if prev else False),
                normalize_severity(sev) or (prev.severity if prev else ""),
                max(score, epss.get(cve, 0.0)),
            )
    return sorted(found.values(), key=lambda c: (not c.kev, -c.epss, c.cve))


def _classify(
    upd: Update,
    cves: Sequence[Cve],
    enabled: Mapping[str, bool],
    severities: Sequence[str],
    epss_threshold: float | None,
) -> str:
    if enabled["zero_day"] and any(c.kev for c in cves):
        return "zero_day"
    if enabled["critical"]:
        if upd.severity and upd.severity in severities and upd.security:
            return "critical"
        for c in cves:
            if c.severity and c.severity in severities:
                return "critical"
            if epss_threshold is not None and c.epss * 100.0 >= epss_threshold:
                return "critical"
    if upd.security or cves:
        return "security"
    return "normal"


def check_linux_updates_pending(item: str, params: Mapping[str, Any], section: Section) -> CheckResult:
    now = time.time()
    ensure_threatdb_fresh(now)
    ignore = [re.compile(p) for p in params.get("ignore", []) if p]
    severities = [s.lower() for s in params.get("critical_severities", [])]
    epss_threshold = params.get("epss_threshold")
    configs = {t: _tier_config(params, t) for t in TIERS}
    enabled = {t: configs[t] is not None for t in TIERS}

    eco = ecosystem_from_host(section.os_id, section.os_version) if section.backend == "apt" else None
    db = load_ecosystem(eco) if eco else None
    kev, epss = load_cve_info()

    rated: list[Rated] = []
    ignored: list[Update] = []
    for upd in section.updates:
        if any(p.search(upd.package) for p in ignore):
            ignored.append(upd)
            continue
        cves = _cves_for(upd, db, kev, epss)
        tier = _classify(upd, cves, enabled, severities, epss_threshold)
        age = _age(now, upd.first_seen)
        cfg = configs[tier] or DEFAULT_PENDING["tier_normal"]
        rated.append(Rated(upd, tier, age, cves, _tier_state(cfg, age)))

    if not rated and not section.removals and not section.withheld and not section.held:
        yield Result(state=State.OK, summary="No updates pending")
    for tier in TIERS:
        items = [r for r in rated if r.tier == tier]
        if not items:
            continue
        oldest = max(r.age for r in items)
        due = [r for r in items if r.state is not State.OK]
        text = f"{TIER_TITLES[tier]}: {len(items)} (oldest {render.timespan(oldest)})"
        if due and len(due) != len(items):
            text += f", {len(due)} overdue"
        if tier in ("zero_day", "critical"):
            ids = sorted({c.cve for r in items for c in r.cves if (tier == "critical" or c.kev)})
            if ids:
                text += f" [{', '.join(ids[:3])}{', ...' if len(ids) > 3 else ''}]"
        yield Result(state=State.worst(*(r.state for r in items)), summary=text)

    kept = [r for r in rated if r.update.kind in ("dist", "new")]
    if kept and section.backend == "apt":
        yield Result(state=State.OK, summary=f"only via dist-upgrade: {len(kept)}")
    if section.removals:
        yield Result(
            state=_state(params.get("removals_state", 0)),
            summary=f"removals by dist-upgrade: {len(section.removals)}",
        )
    phased = [p for p, reason in section.withheld if reason == "phased"]
    other_withheld = [p for p, reason in section.withheld if reason != "phased"]
    if phased:
        yield Result(state=State.OK, summary=f"phased (deferred by Ubuntu): {len(phased)}")
    if other_withheld:
        yield Result(
            state=_state(params.get("withheld_state", 0)),
            summary=f"kept back, not installable: {len(other_withheld)}",
        )
    if section.held:
        yield Result(state=_state(params.get("held_state", 0)), summary=f"held/locked: {len(section.held)}")
    if ignored:
        yield Result(state=State.OK, notice=f"ignored by rule: {len(ignored)}")
    for kind in ("snap", "flatpak"):
        apps = [a for a in section.apps if a[0] == kind]
        if apps:
            yield Result(
                state=_state(params.get("apps_state", 0)),
                summary=f"{kind} updates: {len(apps)}",
            )
            for _k, name, version in apps:
                yield Result(state=State.OK, notice=f"{kind}: {name} -> {version}")
    if eco and db is None:
        yield Result(
            state=State.OK,
            notice="no threat data for this release - zero-day/critical from CVE versions inactive "
            "(see Repository Health service)",
        )
    if not kev and (enabled["zero_day"] or enabled["critical"]):
        yield Result(state=State.OK, notice="no KEV/EPSS data on this site (see Repository Health service)")

    order = {t: i for i, t in enumerate(TIERS)}
    for r in sorted(rated, key=lambda x: (order[x.tier], -x.age, x.update.package)):
        u = r.update
        info = f"{TIER_TITLES[r.tier]}, open {render.timespan(r.age)}"
        if u.kind == "dist":
            info += ", dist-upgrade only"
        elif u.kind == "new":
            info += ", new package"
        if u.severity:
            info += f", severity {u.severity}"
        if u.advisories:
            info += f", {u.advisories}"
        if r.cves:
            kev_ids = [c.cve for c in r.cves if c.kev]
            shown = kev_ids + [c.cve for c in r.cves if not c.kev]
            info += f", fixes {', '.join(shown[:5])}{' ...' if len(shown) > 5 else ''}"
            if kev_ids:
                info += " (actively exploited)"
        yield Result(state=r.state, notice=f"{u.package} {u.installed or '-'} -> {u.candidate} ({info})")
    for pkg, ver in section.removals:
        yield Result(state=State.OK, notice=f"{pkg} {ver} would be removed by dist-upgrade")
    for pkg in phased:
        yield Result(state=State.OK, notice=f"{pkg}: phased update, deferred by Ubuntu")
    for pkg in other_withheld:
        yield Result(state=State.OK, notice=f"{pkg}: kept back")
    for pkg in section.held:
        yield Result(state=State.OK, notice=f"{pkg}: held/locked")
    for u in ignored:
        yield Result(state=State.OK, notice=f"{u.package} {u.installed} -> {u.candidate}: ignored by rule")

    sec_items = [r for r in rated if r.tier != "normal"]
    yield Metric("linux_updates_zero_day", sum(1 for r in rated if r.tier == "zero_day"))
    yield Metric("linux_updates_critical", sum(1 for r in rated if r.tier == "critical"))
    yield Metric("linux_updates_security", sum(1 for r in rated if r.tier == "security"))
    yield Metric("linux_updates_normal", sum(1 for r in rated if r.tier == "normal"))
    yield Metric("linux_updates_security_age", max((r.age for r in sec_items), default=0.0))


check_plugin_linux_updates_pending = CheckPlugin(
    name="linux_updates_pending",
    service_name="%s Pending Updates",
    sections=["linux_updates"],
    discovery_function=discover_linux_updates,
    check_function=check_linux_updates_pending,
    check_ruleset_name="linux_updates_pending",
    check_default_parameters=DEFAULT_PENDING,
)

# ========================================================== reboot required

DEFAULT_REBOOT: dict[str, Any] = {"state": 1, "restart_state": 0}

REBOOT_TITLES = {
    "flag": "reboot-required flag",
    "tool": "package manager reports reboot required",
    "kernel": "newer kernel installed",
    "modules": "modules of running kernel missing",
}


def check_linux_updates_reboot(item: str, params: Mapping[str, Any], section: Section) -> CheckResult:
    now = time.time()
    if section.container != "none":
        yield Result(
            state=State.OK,
            summary=f"Not applicable inside a container ({section.container}), the host's kernel applies",
        )
    elif not section.reboot:
        yield Result(state=State.OK, summary="No reboot required")
    else:
        stamps = [ts for _k, ts, _d in section.reboot if ts > 0]
        age = _age(now, min(stamps)) if stamps else 0.0
        state = _state(params.get("state", 1))
        kernel_only = all(k == "kernel" for k, _ts, _d in section.reboot)
        livepatched = section.livepatch_state in ("applied", "loaded")
        if kernel_only and livepatched and params.get("livepatch_state") is not None:
            state = _state(params["livepatch_state"])
        esc = params.get("escalate")
        if esc and stamps and age >= float(esc.get("after", 0.0)):
            state = State.worst(state, _state(esc.get("state", 2)))
        reasons = ", ".join(REBOOT_TITLES.get(k, k) for k, _ts, _d in section.reboot)
        text = f"Reboot required: {reasons}"
        if stamps:
            text += f" (since {render.timespan(age)})"
        yield Result(state=state, summary=text)
        for kind, _ts, detail in section.reboot:
            if detail:
                yield Result(state=State.OK, notice=f"{REBOOT_TITLES.get(kind, kind)}: {detail}")
        yield Metric("linux_updates_reboot_age", age)
    if section.livepatch_source:
        text = f"kernel livepatch ({section.livepatch_source}): {section.livepatch_state or 'unknown'}"
        if section.livepatch_modules:
            text += f", modules: {section.livepatch_modules}"
        yield Result(state=State.OK, notice=text)
    if section.restart:
        yield Result(
            state=_state(params.get("restart_state", 0)),
            summary=f"services to restart: {len(section.restart)}",
        )
        for svc in section.restart:
            yield Result(state=State.OK, notice=f"needs restart: {svc}")


check_plugin_linux_updates_reboot = CheckPlugin(
    name="linux_updates_reboot",
    service_name="%s Reboot Required",
    sections=["linux_updates"],
    discovery_function=discover_linux_updates,
    check_function=check_linux_updates_reboot,
    check_ruleset_name="linux_updates_reboot",
    check_default_parameters=DEFAULT_REBOOT,
)

# ========================================================= repository health

DEFAULT_REPOS: dict[str, Any] = {
    "cache_age": ("fixed", (259200.0, 604800.0)),
    "refresh_failed_state": 1,
    "refresh_warnings_state": 0,
    "errors_state": 1,
    "no_security_info_state": 1,
    "foreign_suite_state": 1,
    "duplicate_sources_state": 0,
    "legacy_keyring_state": 0,
    "broken_packages_state": 1,
    "orphans_state": 0,
    "auto_missing_state": 0,
    "auto_errors_state": 0,
    "eol_state": 1,
    "threatdb_age": ("fixed", (172800.0, 604800.0)),
    "threatdb_missing_state": 1,
}

_SUITE_SUFFIX = re.compile(r"-(security|updates|backports|proposed|infra-security|apps-security)$")


def _is_security_repo(repo: Repo) -> bool:
    return (
        repo.archive.endswith("-security")
        or repo.codename.endswith("-security")
        or "security" in repo.label.lower()
        or "/updates" in repo.location
    )


def check_linux_updates_repos(item: str, params: Mapping[str, Any], section: Section) -> CheckResult:
    now = time.time()
    yield Result(state=State.OK, notice=f"package manager: {section.backend}, plug-in {section.plugin_version}")

    # metadata
    if section.cache_ts > 0:
        yield from check_levels(
            _age(now, section.cache_ts),
            levels_upper=params.get("cache_age"),
            metric_name="linux_updates_cache_age",
            render_func=render.timespan,
            label="Package metadata refreshed",
        )
    else:
        yield Result(
            state=_state(params.get("refresh_failed_state", 1)),
            summary="Package metadata refresh time unknown",
        )
    if section.refresh_mode == "auto":
        if section.refresh_status in ("failed", "timeout"):
            yield Result(
                state=_state(params.get("refresh_failed_state", 1)),
                summary=f"last refresh {section.refresh_status} "
                f"({render.timespan(_age(now, section.refresh_ts))} ago)",
            )
        elif section.refresh_status == "warnings":
            yield Result(
                state=_state(params.get("refresh_warnings_state", 0)),
                summary="last refresh with warnings",
            )
        elif section.refresh_status == "noroot":
            yield Result(
                state=State.OK,
                notice="Agent does not run as root: metadata refresh skipped "
                "(relies on the system's own update timer)",
            )
    errors = [t for lvl, t in section.messages if lvl == "E"]
    warnings = [t for lvl, t in section.messages if lvl == "W"]
    dupes = [t for t in warnings if "configured multiple times" in t or "listed more than once" in t]
    legacy = [t for t in warnings if "legacy trusted.gpg" in t.lower()]
    other_w = [t for t in warnings if t not in dupes and t not in legacy]
    if errors:
        yield Result(
            state=_state(params.get("errors_state", 1)),
            summary=f"package manager errors: {len(errors)} ({errors[0][:120]})",
        )
    if dupes:
        yield Result(
            state=_state(params.get("duplicate_sources_state", 0)),
            summary=f"duplicate sources: {len(dupes)}",
        )
    if section.legacy_keyring or legacy:
        yield Result(
            state=_state(params.get("legacy_keyring_state", 0)),
            summary="legacy keyring /etc/apt/trusted.gpg in use",
        )

    # security information
    if section.backend == "apt":
        if section.repos and not any(_is_security_repo(r) for r in section.repos):
            yield Result(
                state=_state(params.get("no_security_info_state", 1)),
                summary="no security repository configured - security updates cannot be detected",
            )
        foreign = sorted(
            {
                f"{r.location} (suite {r.codename})"
                for r in section.repos
                if r.origin in ("Debian", "Ubuntu", "Debian-Security")
                and r.codename
                and section.os_codename
                and _SUITE_SUFFIX.sub("", r.codename) != section.os_codename
            }
        )
        if foreign:
            yield Result(
                state=_state(params.get("foreign_suite_state", 1)),
                summary=f"repositories of a different release: {len(foreign)}",
            )
            for item in foreign:
                yield Result(state=State.OK, notice=f"foreign suite: {item}")
    elif section.secinfo is False:
        yield Result(
            state=_state(params.get("no_security_info_state", 1)),
            summary=f"no security advisory data ({section.secinfo_detail}) - "
            "security updates cannot be detected",
        )
    elif section.secinfo:
        yield Result(state=State.OK, notice=f"security information: {section.secinfo_detail}")
    if section.repos:
        yield Result(state=State.OK, notice=f"enabled repositories: {len({r.location for r in section.repos})}")

    # package database
    if section.audit_count:
        text = f"package database problems: {section.audit_count}"
        if section.audit_detail:
            text += f" ({section.audit_detail})"
        yield Result(state=_state(params.get("broken_packages_state", 1)), summary=text)
    if section.autoremove:
        kernels = [p for p in section.autoremove if p.startswith(("linux-image", "linux-headers", "linux-modules", "kernel"))]
        yield from check_levels(
            len(section.autoremove),
            levels_upper=params.get("autoremove_levels"),
            metric_name="linux_updates_autoremove",
            render_func=lambda v: f"{int(v)}",
            label="autoremovable packages",
        )
        if kernels:
            yield Result(state=State.OK, notice=f"old kernel packages: {', '.join(kernels)}")
    if section.orphans:
        yield Result(
            state=_state(params.get("orphans_state", 0)),
            summary=f"packages from no repository: {len(section.orphans)}",
        )
        yield Result(state=State.OK, notice=f"orphaned/local packages: {', '.join(section.orphans[:30])}")

    # automatic updates
    if section.auto_name not in ("", "-"):
        if not (section.auto_installed and section.auto_enabled):
            yield Result(
                state=_state(params.get("auto_missing_state", 0)),
                summary=f"{section.auto_name} " + ("not enabled" if section.auto_installed else "not installed"),
            )
        else:
            yield Result(state=State.OK, notice=f"automatic updates: {section.auto_name} enabled")
            if section.auto_last_run > 0:
                yield from check_levels(
                    _age(now, section.auto_last_run),
                    levels_upper=params.get("auto_age"),
                    render_func=render.timespan,
                    label=f"{section.auto_name} last run",
                    notice_only=params.get("auto_age") is None,
                )
            if section.auto_errors:
                yield Result(
                    state=_state(params.get("auto_errors_state", 0)),
                    summary=f"{section.auto_name} errors in last run: {section.auto_errors}",
                )

    # last real upgrade
    if section.last_upgrade > 0:
        yield from check_levels(
            _age(now, section.last_upgrade),
            levels_upper=params.get("last_upgrade_age"),
            render_func=render.timespan,
            label="last package change",
            notice_only=params.get("last_upgrade_age") is None,
        )

    # OS end of life (site data from endoflife.date, else distro-info on the host)
    eol = lookup_eol(section.os_id, section.os_version) or section.eol_host
    if eol:
        try:
            eol_ts = time.mktime(time.strptime(eol, "%Y-%m-%d"))
        except ValueError:
            eol_ts = 0.0
        if eol_ts and eol_ts <= now:
            yield Result(
                state=_state(params.get("eol_state", 1)),
                summary=f"{section.os_id} {section.os_version} is end of life since {eol}",
            )
        elif eol_ts:
            yield Result(state=State.OK, notice=f"OS supported until {eol}")
            warn_before = params.get("eol_warn_before")
            if warn_before is not None and eol_ts - now < float(warn_before):
                yield Result(
                    state=State.WARN,
                    summary=f"OS end of life in {render.timespan(eol_ts - now)} ({eol})",
                )

    # threat data
    meta = load_meta()
    if meta is None:
        yield Result(
            state=_state(params.get("threatdb_missing_state", 1)),
            summary="threat data missing - download is started automatically, see ~/var/log/linux_updates_threatdb.log",
        )
    else:
        sources = meta.get("sources", {})
        needed = ["kev", "epss"] + (["osv_debian", "osv_ubuntu"] if section.backend == "apt" else [])
        stamps = [float(sources.get(n, {}).get("last_success", 0)) for n in needed]
        if not stamps or min(stamps) <= 0:
            yield Result(state=_state(params.get("threatdb_missing_state", 1)), summary="threat data incomplete")
        else:
            yield from check_levels(
                _age(now, min(stamps)),
                levels_upper=params.get("threatdb_age"),
                render_func=render.timespan,
                label="threat data age",
            )
    for t in other_w[:10]:
        yield Result(state=State.OK, notice=f"warning: {t[:300]}")
    for t in errors[:10]:
        yield Result(state=State.OK, notice=f"error: {t[:300]}")


check_plugin_linux_updates_repos = CheckPlugin(
    name="linux_updates_repos",
    service_name="%s Repository Health",
    sections=["linux_updates"],
    discovery_function=discover_linux_updates,
    check_function=check_linux_updates_repos,
    check_ruleset_name="linux_updates_repos",
    check_default_parameters=DEFAULT_REPOS,
)

# ================================================================ inventory

INV_PATH = ["software", "applications", "linux_updates"]


def inventory_linux_updates(section: Section) -> InventoryResult:
    """HW/SW inventory: pending updates and the CVEs they fix.

    Makes "which hosts are affected by CVE-…" and "where is package X still
    unpatched" searchable in the inventory views. Classification uses the
    default tier settings and the threat data of the site.
    """
    severities = list(DEFAULT_PENDING["critical_severities"])
    epss_threshold = DEFAULT_PENDING["epss_threshold"]
    enabled = {t: True for t in TIERS}
    eco = ecosystem_from_host(section.os_id, section.os_version) if section.backend == "apt" else None
    db = load_ecosystem(eco) if eco else None
    kev, epss = load_cve_info()

    counts = dict.fromkeys(TIERS, 0)
    for upd in section.updates:
        cves = _cves_for(upd, db, kev, epss)
        tier = _classify(upd, cves, enabled, severities, epss_threshold)
        counts[tier] += 1
        yield TableRow(
            path=INV_PATH + ["pending"],
            key_columns={"package": upd.package},
            inventory_columns={
                "installed": upd.installed,
                "candidate": upd.candidate,
                "source_package": upd.source,
                "kind": {"up": "upgrade", "dist": "dist-upgrade only", "new": "new package"}.get(upd.kind, upd.kind),
                "tier": TIER_TITLES[tier],
                "security": "yes" if upd.security else "no",
                "severity": upd.severity,
                "advisories": upd.advisories,
                "cves": ", ".join(c.cve for c in cves),
                "actively_exploited": ", ".join(c.cve for c in cves if c.kev),
                "repository": upd.origin,
                "first_seen": int(upd.first_seen),
            },
        )
        for c in cves:
            yield TableRow(
                path=INV_PATH + ["cves"],
                key_columns={"cve": c.cve, "package": upd.package},
                inventory_columns={
                    "actively_exploited": "yes" if c.kev else "no",
                    "severity": c.severity,
                    "epss": round(c.epss * 100.0, 2),
                    "installed": upd.installed,
                    "fixed_by": upd.candidate,
                },
            )
    auto = "-"
    if section.auto_name not in ("", "-"):
        auto = f"{section.auto_name}: " + (
            "enabled" if section.auto_installed and section.auto_enabled
            else "disabled" if section.auto_installed else "not installed"
        )
    yield Attributes(
        path=INV_PATH,
        inventory_attributes={
            "package_manager": section.backend,
            "plugin_version": section.plugin_version,
            "automatic_updates": auto,
            "os_end_of_life": lookup_eol(section.os_id, section.os_version) or section.eol_host or "",
            "livepatch": f"{section.livepatch_source}: {section.livepatch_state}" if section.livepatch_source else "",
        },
        status_attributes={
            "pending_total": len(section.updates),
            "pending_zero_day": counts["zero_day"],
            "pending_critical": counts["critical"],
            "pending_security": counts["security"],
            "pending_normal": counts["normal"],
            "reboot_required": "yes" if section.reboot and section.container == "none" else "no",
            "held_packages": len(section.held),
            "snap_flatpak_updates": len(section.apps),
        },
    )


inventory_plugin_linux_updates = InventoryPlugin(
    name="linux_updates",
    sections=["linux_updates"],
    inventory_function=inventory_linux_updates,
)
