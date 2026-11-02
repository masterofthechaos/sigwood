# DEVLOG — sigwood-adg

Durable history, **newest first**. Entries are append-only: content is frozen once written; only status
badges/checkboxes update. This is the source of truth for what happened and why, for work done in *this*
local checkout — not a replacement for upstream's own history (see `git log`, `CHANGELOG.md`).

---

## 2026-11-02 — Local repository-attention digest implemented and verified
- **By:** Polo, at Micah's direction to make Sigwood useful for managing his other repositories.
- **Scope:** experimental, fork-local `sigwood repos PATH --format=text|json`; a factual offline
  attention digest, not a network-security detector, graph rewrite, or autonomous repository manager.
  Started from verified fork main `cd21b865a3f2eb225e22e23428cff74df9dc2310`; upstream authorship,
  license, detectors and existing source families remain intact.
- **Change:** strict versioned NDJSON schema; pure deterministic analysis and rendering; exact-head
  check evidence, conflicts, drafts and explicit coverage/unknown states. Separate optional
  `tools/repository_snapshot.py` collects explicit repository allowlists via GET-only GitHub CLI
  calls, paginating check runs and legacy statuses without tokens or raw responses in artifacts.
  The analyzer never imports the collector, executes repository configuration, contacts a network,
  or claims merge readiness. Synthetic demo, golden outputs, schema/usage/privacy documentation,
  adversarial and real-process offline tests included.
- **Version:** `0.2.1+repos.1` in `sigwood/__init__.py`; local-version capability bump against the
  unchanged upstream 0.2.1 base, not an upstream or PyPI release.
- **Verified:** fresh-main baseline **2,376 passed / 11 skipped**; final aggregate
  `python -m pytest -ra` **2,617 passed / 11 skipped**. Skips match baseline: optional PDF/Pango,
  eight redundant recognizer self-match cases, one source-resolution coverage note, and one absent
  dev-box residue list. All **241 new tests** pass. Built wheel and ran its module entry point
  outside the checkout: version correct and synthetic demo JSON byte-identical to reviewed golden.
  A real collector process driven by a fake, credential-free `gh` executable feeds the real analyzer;
  audit-hook tests prohibit analyzer network, subprocess, configuration and prompt side effects.
  Independent review caught and fixed Unicode output controls and collection identity validation;
  aggregate voice tripwire caught and corrected a documentation flag spelling.
- **Limits:** no live authenticated collector run or private snapshot validation was attempted.
  Snapshots are unverified, non-atomic assertions; required policies, reviews, owner holds and
  test-merge commit checks remain unassessed. Collector source script is checkout-only, not a wheel
  service/entry point. No new dependency, paid API call, repository mutation, push, merge or deploy.
- **Other work:** AdGuard implementation was paused when Micah redirected this work. Its separate
  local commits/worktrees are preserved and clean; no AdGuard changes enter this branch.
- **Release path:** local reviewable commits only, per governance; no publication implied. See
  `docs/REPOSITORY_ATTENTION.md` for exact contract, safe collection and verification commands.

---

## 2026-07-13 — AdGuard DNS Query Log support: design decided, not yet implemented
- **By:** Claude, at Micah's direction — design conversation only, no code written.
- **Change:** worked out a full design for adding AdGuard DNS (cloud) Query Log parsing as a new sigwood
  source family, grounded in an actual ~2.5M-line export (`time_iso`/`device`/`domain`/`status`/`rcode`/
  `rrtype`/`dnssec`/`proto`/`company`/`client_country`/`response_country` NDJSON — the cloud AdGuard DNS
  product, not AdGuard Home, which has an unrelated schema). Scope confirmed as the **full family**:
  - `parsers/adguard.py` (`parse_line`/`sniff`), registered in the sniff cascade.
  - Loader wiring: `adguard_dir` source key, an NDJSON-**accepting** skip guard (inverse of Pi-hole's
    NDJSON-**rejecting** guard, since AdGuard's export is itself NDJSON).
  - `digest/dns.py`'s feed model generalized from its current hardcoded zeek-vs-pihole binary to a real
    third `feed="adguard"` branch — AdGuard carries both a string `rcode` (NXDOMAIN via
    `RcodeNameError`, not zeek's numeric `3`) and a genuine per-row block/allow `status`, so it can drive
    both the nxdomain-rate and block-rate slots simultaneously, unlike either existing feed alone.
  - `graph/adguard.py`, a disposition-spine graph mirroring `graph/pihole.py`:
    `{REQUEST,RESPONSE}_BLOCKED → blocked`, `{REQUEST,RESPONSE}_ALLOWED → allowed`, `NONE → resolved`.
  - Detector wiring (`detectors/dns.py` `OPTIONAL_LOGS`, `detectors/dnsblock.py`) and config/CLI/wizard
    surfaces (`common/config.py`, `cli.py`, `cli_init.py`).
  - Touches ~12 files, append-only against the existing zeek/syslog/pihole/cloudtrail family pattern;
    no existing source path changes.
- **Verified:** design only — no code exists yet. This will be the fork's first real divergence from
  upstream (`AGENTS.md` "Fork" section currently reads "none yet" — update that ledger when
  implementation lands) and is a user-observable capability owing a version bump
  (`sigwood/__init__.py`) once shipped.

---

## 2026-07-13 — Governance surface established on an adopted checkout
- **By:** Bob (`/bob`) at Micah's direction.
- **Change:** established the AI-agent governance surface (`AGENTS.md`, this file, `docs/DEVLOG-EXPRESS.md`,
  `docs/bulletins/`) on top of the existing sigwood codebase (v0.2.1), which is an unmodified clone of
  upstream https://github.com/helixmap/sigwood pulled in to support local feature work. No functional
  code was touched. `docs/STATE.md` was delegated to `/groundhog`; solo tier does not include
  `docs/Roadmaps/` or session-punch-cards (see `AGENTS.md`).
- **Verified:** structure created; no baseline score yet — run `/clinic <repo> --phase intake` for one.
