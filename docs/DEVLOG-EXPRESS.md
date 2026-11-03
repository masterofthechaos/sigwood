# DEVLOG-EXPRESS — sigwood-adg

Terse current-state scan. Points back to `docs/DEVLOG.md` for detail. Keep footer date in sync with DEVLOG.

- **Version:** 0.2.1+repos.1 (`sigwood/__init__.py`), a fork-local suffix on upstream 0.2.1.
- **Now:** experimental `sigwood repos` read-only repository-attention digest; deterministic
  exact-head check/conflict/draft/unknown reports from versioned NDJSON. Separate opt-in
  GET-only GitHub CLI collector. Upstream threat-hunting behavior is unchanged.
- **Verified:** fresh Linux/Python 3.12 checkout and clean tracked export each passed
  2,617 tests / 11 baseline-equivalent skips. Four deliberate regressions were caught.
  A clean installed wheel outside the checkout matched synthetic golden output and
  analyzed a current public PR snapshot normalized from live connector GET responses.
- **Limits:** no hosted CI runs/checks were present on the verified feature head; no hosted
  CI success, authenticated gh transport run, or other-platform test is claimed.
- **Distribution:** fork-local installable wheel plus full Git source archive; no upstream,
  PyPI, or tagged GitHub release. PR #1 records publication status. Use the separate-venv
  instructions in `docs/REPOSITORY_ATTENTION.md`; checkout-only collector/demo/tests are
  supplied by the full archive, not the wheel or Python sdist.
- **Other work:** AdGuard design remains historical; partial implementation is paused on
  separate branches, not integrated here. Generated `docs/STATE.md` remains untouched.
- **Next:** use explicit repository snapshots and re-check live policy/review/owner state
  before acting on observations. No integration or recurring collection is installed.

_As of 2026-11-03._
