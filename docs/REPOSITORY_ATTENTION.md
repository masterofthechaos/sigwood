# Repository attention digest — experimental fork extension

`sigwood repos` helps answer **which captured pull requests need a closer look?**
It summarizes an explicit, local repository snapshot into deterministic text or
JSON: observed merge conflicts, failed or pending checks, drafts, and unknowns.
This is a small local-use addition to David Augros's Sigwood, not a change in
upstream stewardship or a replacement for GitHub. Network threat detectors and
graphs are unchanged; repository snapshots are not fabricated network flows.

## Install the fork distribution

Version `0.2.1+repos.1` is a fork-local build, not an upstream or PyPI release.
The fork distribution pairs an installable wheel with a complete Git source
archive. The wheel installs `sigwood repos`; the source archive supplies the
optional collector, synthetic demo, tests, and documentation. A Python source
package (sdist) alone does not include those checkout-only files.

After extracting the distribution ZIP, install into a **new, separate** virtual
environment so an existing upstream installation is preserved. Python 3.11+
is declared by the project; this fork build was verified on Linux/Python 3.12.
Dependency installation can use the network; analyzing a snapshot does not.

```bash
python3 -m venv .venv-sigwood-repos
. .venv-sigwood-repos/bin/activate
python -m pip install ./sigwood-0.2.1+repos.1-py3-none-any.whl
tar -xzf sigwood-source.tar.gz
sigwood --version
sigwood repos sigwood-source/demo/repository-attention.ndjson
sigwood repos sigwood-source/demo/repository-attention.ndjson --format=json
```

The optional collector is then `sigwood-source/tools/repository_snapshot.py`.
The wheel does not install or run it automatically. Check the bundle's
`SHA256SUMS` and `VERIFICATION.json` for the source commit and artifact receipt.
For code review or development, use the fork checkout instead:

```bash
git clone https://github.com/masterofthechaos/sigwood.git
cd sigwood
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
sigwood repos demo/repository-attention.ndjson
sigwood repos demo/repository-attention.ndjson --format=json
```

## Try it without credentials or a network

The demo is entirely synthetic. The analyzer reads exactly one regular UTF-8
file and writes only stdout. There is no directory discovery, config loading,
prompt, subprocess, credential access, network request, daemon, or repository
mutation. Only `--help` and `--format text|json` are supported. Invalid input
exits 1 with a line-numbered, payload-redacted error. A valid report exits 0;
**that exit code is not a CI gate or permission to merge.**

## Collect separately, only when you choose

The optional checkout script uses an **already installed and authenticated**
[GitHub CLI](https://cli.github.com/manual/gh_api). It only makes REST GET
requests to `github.com` for the explicit repositories supplied. It never
clones repositories, sources their scripts/configuration, reads token files,
changes issues/PRs, starts CI, merges, pushes, or deploys. Agent-Campus or another
trusted collection process can instead emit the same format; no integration
with Agent-Campus has been installed or claimed.

Run the example below from the fork checkout. If using the distribution bundle,
first run `cd sigwood-source` from the extracted bundle directory.

```bash
# Choose a private location OUTSIDE any source repository.
mkdir -p "$HOME/.local/share/sigwood"
umask 077
python tools/repository_snapshot.py example/widget example/service \
  > "$HOME/.local/share/sigwood/repository-attention.ndjson"
sigwood repos "$HOME/.local/share/sigwood/repository-attention.ndjson"
```

Replace the example repository names with the explicit repositories you want
to inspect. Authentication and permissions remain managed by `gh`; the script
never accepts or prints a token. Required read capabilities are Pull requests,
Checks, and Commit statuses. API errors, permission failures, timeouts, malformed
rows, pagination truncation, and changing response totals remain visibly
`partial` or `unavailable`; they are not an empty healthy result. Exit 2 means a
valid snapshot was written but some collection coverage is incomplete. Exit 1
means invalid arguments or no valid artifact could be emitted. The script does
not automatically retry a failed request or conceal a failed page.

Collection is **non-atomic**: PRs can change or close while requests are in
flight. `observed_at` is collection completion time, not an attestation that all
rows were current at that instant. The collector fetches PR details, queries
both check APIs by the captured 40-character head SHA, and verifies each check
run's returned SHA. A failed detail request preserves the listed head with
unknown mergeability and partial repository coverage. Heads may advance after
capture; always revisit the linked PR and exact commit before acting.

GitHub check runs and legacy commit statuses are separate evidence streams.
The collector paginates both, requests `filter=latest` check runs, and keeps only
the newest legacy status per case-insensitive context. It does not mistake the
combined-status API's empty `pending` aggregate for a real pending check.
Pagination is bounded to 100 pages per endpoint, with 100 items per page;
repeated pages and reached limits are partial. Requests time out after 60
seconds. The check-runs endpoint itself has a 1000-suite visibility limit; a
captured set reaching that boundary is marked partial. See GitHub's official
[check-run contract](https://docs.github.com/en/rest/checks/runs#list-check-runs-for-a-git-reference),
[legacy status order/context semantics](https://docs.github.com/en/rest/commits/statuses),
and [tri-state mergeability](https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request).

**Privacy:** snapshots and reports may still identify private repositories,
PR numbers, commit SHAs and check names. Treat both as private. Titles, bodies,
authors, comments, logs, provider URLs and raw responses are deliberately not
exported, but this is data minimization, not anonymization. Do not commit real
snapshots, copy them into public fixtures, or upload them for analysis without
separate permission. Errors do not echo raw provider output or input payloads.

## Version 1 input contract

The first nonblank NDJSON line is exactly this versioned header shape:

```json
{"schema":"sigwood.repository-attention","version":1,"type":"snapshot","observed_at":"2026-01-01T00:00:00Z","repositories":[{"repository":"example/widget","pull_requests":"complete"}]}
```

It declares a nonempty explicit repository list. Each coverage value is
`complete`, `partial`, or `unavailable`. A complete repository with no following
PR rows means no open PRs were reported; an unavailable repository means **not
known**, not zero. Repository names are case-insensitive and normalized to
lowercase. Timestamp must include a timezone and is normalized to UTC.

Each following nonblank line has this complete PR shape (all fields required):

```json
{"type":"pull_request","repository":"example/widget","number":1,"head_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","draft":false,"mergeable":null,"checks":{"head_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","check_runs":{"coverage":"complete","items":[{"name":"tests","status":"completed","conclusion":"success"}]},"statuses":{"coverage":"complete","items":[]}}}
```

- PR numbers are positive integers; booleans are not accepted as integers.
- Both SHAs are full 40-character hexadecimal values. Check evidence SHA may
  be `null` when unknown. No supplied branch name is resolved by the analyzer.
- `draft` and `mergeable` are `true`, `false`, or `null` (unknown).
- Check-run items contain exactly `name`, `status`, `conclusion`; legacy items
  exactly `name`, `state`. Conclusion may be `null`. Unknown future state names
  are retained as unknown evidence, never treated as success.
- An unavailable group cannot contain items. Rows must belong to a declared,
  non-unavailable repository. Supplied coverage is an assertion by the producer,
  not something offline Sigwood can verify against GitHub.
- Unknown fields, duplicate JSON keys, unsupported versions, malformed records,
  control characters, contradictory duplicate PR rows, and invalid types are
  rejected. Identical normalized PR rows and identical check items deduplicate.
  Distinct results sharing a check name are retained; no last-write-wins policy.
- Bounds: 1 MiB per line, 64 MiB per snapshot, 100,000 PR records. There is no
  silent truncation. Blank lines are allowed and still count toward byte bounds.

The complete input is validated before any report is printed. Same normalized
evidence produces byte-identical text/JSON regardless of input row order,
machine timezone, local configuration, or current time. JSON output uses schema
`sigwood.repository-attention-report`, version `1`.

## What the observations mean — and do not mean

| Observation | Meaning |
| --- | --- |
| `conflict` | Captured `mergeable` was false. |
| `no_conflict_observed` | Captured `mergeable` was true; not permission or readiness to merge. |
| `unknown` mergeability | GitHub had not computed it, collection failed, or producer did not know. |
| `failure_observed` | Exact-head completed run reported failure/timed_out/cancelled/action_required/startup_failure/stale, or legacy status failure/error. The underlying state is shown; cancellation is not labeled a failed test. |
| `pending_observed` | An actual exact-head run/status reported pending activity. |
| `success_observed` | At least one exact-head result exists, both API groups claim complete coverage, and every observed result is success. |
| `unknown` checks | No evidence, missing/stale head, incomplete coverage, neutral/skipped result, or an unrecognized state prevents a success observation. |

Failure observations take precedence over pending, then unknown, then success.
Incomplete coverage is always retained even if an observed failure/pending state
is useful. A mismatched or missing evidence SHA makes the overall check state
unknown: stale success **and** stale failure cannot be promoted to the captured
PR head. Draft state stays separate from check and conflict state.

**Not assessed:** required-check policy, branch protection/rulesets, test-merge
commit checks, reviews, owner holds, assignments, local worktrees, issue
triage, security vulnerabilities, release readiness, or permission to mutate
anything. All links are derived from validated identifiers, not proof of
existence or authenticity. No score recommends a merge; no repair is performed.

## Verification and scope

Run `python -m pytest -ra` from the checkout. Pure parser/policy/render tests,
CLI no-side-effect tests, adversarial invariants, and mocked collector transport
tests require no account, network, browser, paid API, or private snapshot.
The source-checkout collector is optional and is not installed as an automatic
service or included as a wheel entry point. AdGuard work remains on separate
paused branches and is not part of this capability.
