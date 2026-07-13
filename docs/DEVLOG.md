# DEVLOG — sigwood-adg

Durable history, **newest first**. Entries are append-only: content is frozen once written; only status
badges/checkboxes update. This is the source of truth for what happened and why, for work done in *this*
local checkout — not a replacement for upstream's own history (see `git log`, `CHANGELOG.md`).

---

## 2026-07-13 — Governance surface established on an adopted checkout
- **By:** Bob (`/bob`) at Micah's direction.
- **Change:** established the AI-agent governance surface (`AGENTS.md`, this file, `docs/DEVLOG-EXPRESS.md`,
  `docs/bulletins/`) on top of the existing sigwood codebase (v0.2.1), which is an unmodified clone of
  upstream https://github.com/helixmap/sigwood pulled in to support local feature work. No functional
  code was touched. `docs/STATE.md` was delegated to `/groundhog`; solo tier does not include
  `docs/Roadmaps/` or session-punch-cards (see `AGENTS.md`).
- **Verified:** structure created; no baseline score yet — run `/clinic <repo> --phase intake` for one.
