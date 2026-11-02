# DEVLOG-EXPRESS — sigwood-adg

Terse current-state scan. Points back to `docs/DEVLOG.md` for detail. Keep footer date in sync with DEVLOG.

- **Version:** 0.2.1+repos.1 (`sigwood/__init__.py`), a local fork suffix on upstream 0.2.1.
- **Now:** experimental `sigwood repos` read-only repository-attention digest implemented locally;
  deterministic exact-head check/conflict/draft/unknown reports from versioned NDJSON. Separate
  opt-in GET-only GitHub CLI collector. Upstream threat-hunting behavior is unchanged.
- **Verified:** 2,617 passed / 11 baseline-equivalent skips; built wheel ran outside checkout and
  matched synthetic golden output. No live authenticated collector or private snapshot run claimed.
- **Publication:** committed locally for review only; no push, merge, deploy or upstream release.
- **Other work:** AdGuard design from July remains historical below; partial implementation is
  paused on separate local branches, not integrated here. `docs/STATE.md` is an older generated
  snapshot and has deliberately not been hand-edited.
- **Next:** review the local repository-attention change and its private-data boundaries before
  explicitly running the optional collector on selected repositories. See
  `docs/REPOSITORY_ATTENTION.md` for scope, format and commands.

_As of 2026-11-02._
