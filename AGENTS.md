# AGENTS.md — sigwood-adg governance contract

> The durable contract for agents in this repo. Repo-local current docs outrank cross-project defaults.

## Read order (before non-trivial work)
1. `docs/DEVLOG-EXPRESS.md` — current-state scan (or `docs/STATE.md` for the ~60s version)
2. This file — rules, build/test, non-negotiables
3. `docs/DEVLOG.md` — durable history, newest-first
4. `docs/bulletins/active/` — live defect/decision watch queue, if any

## Trust hierarchy <!-- Lessons #75, rubric P2 -->
- Repo-local current docs (this file, `docs/DEVLOG-EXPRESS.md`, `docs/STATE.md`) win **for this repo**.
- The shared corpus is a cross-project **default**, not local law.
- Current docs beat old audit reports and git archaeology. When two sources disagree, the newer
  repo-local current-state doc wins.

## Shared corpus <!-- reference, never copy -->
Cross-project lessons live in AgentResources: `${AGENT_RESOURCES:-~/Projects/AgentResources}`.
Scan its `Lessons/Lessons-Learned-EXPRESS.md` before novel work. Do **not** copy corpus content here.

## Project
- Type: python
- Scope: production (pre-1.0) · **fork of an upstream repo, not yet forked/pushed on GitHub** · single
  local maintainer working solo. See "Fork" below.
- Version source of truth: `sigwood/__init__.py` → `__version__`. `pyproject.toml` mirrors it via
  `dynamic = ["version"]` / `[tool.setuptools.dynamic] version = {attr = "sigwood.__version__"}` —
  do not hand-set a version anywhere else.
- Build: `pip install -e ".[dev]"` (bare install: `pip install -e .`)
  Test: `python -m pytest -ra`

## Fork <!-- Lessons #84: Fork Governance Ledger -->
- **Purpose:** local clone of someone else's shipped tool, kept to add one or two features for local use
  — not a claim of stewardship over the whole product.
- **Upstream:** https://github.com/helixmap/sigwood (author: David Augros, `code@augros.org`)
- **Local remote:** `origin` still points at the upstream URL above; this checkout has not been pushed
  to a separate fork/remote yet. Treat any `git push` here as touching upstream's repo unless/until the
  remote is repointed — confirm with the user before pushing.
- **Divergence:** none yet. All history through `b033634` ("sigwood 0.2.1") is upstream's, authored by
  David Augros.
- **Source-edit rule:** keep local changes scoped to the intended feature(s); don't restructure or
  rebrand upstream code as part of unrelated work. If divergence grows, update this section.

## Non-negotiables
- Don't hand-edit generated files; edit the source of truth. <!-- #24 -->
- A user-observable capability/behavior change owes a version bump (`sigwood/__init__.py`); record any
  deliberate no-bump. <!-- #27 -->
- Session discipline is governed by the shared `/groundhog` skill (STATE.md) — enforcement lives there,
  not restated here. This repo is solo-tier: no `docs/Roadmaps/` or session-punch-cards were scaffolded.
- Commit, don't push, unless asked — and never push to `origin` without confirming it's the intended
  remote (see Fork, above).
