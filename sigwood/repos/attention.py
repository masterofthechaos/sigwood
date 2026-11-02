"""Deterministic, exact-head observations; never a merge-readiness judgment."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy

FAILURES = {"failure", "timed_out", "cancelled", "action_required", "startup_failure", "stale"}
PENDING = {"queued", "in_progress", "waiting", "pending", "requested"}
STATES = ("failure_observed", "pending_observed", "unknown", "success_observed")


def _run_state(item: dict) -> str:
    if item["status"] in PENDING:
        return "pending_observed"
    if item["status"] == "completed":
        if item["conclusion"] in FAILURES:
            return "failure_observed"
        if item["conclusion"] == "success":
            return "success_observed"
    return "unknown"


def _status_state(item: dict) -> str:
    return {"failure": "failure_observed", "error": "failure_observed",
            "pending": "pending_observed", "success": "success_observed"}.get(item["state"], "unknown")


def _checks(row: dict) -> tuple[str, list[str]]:
    checks = row["checks"]
    reasons = [f"{name}_coverage_{checks[name]['coverage']}" for name in ("check_runs", "statuses")
               if checks[name]["coverage"] != "complete"]
    if checks["head_sha"] is None:
        return "unknown", ["missing_check_head", *reasons]
    if checks["head_sha"] != row["head_sha"]:
        return "unknown", ["stale_check_head", *reasons]
    states = [_run_state(item) for item in checks["check_runs"]["items"]]
    states += [_status_state(item) for item in checks["statuses"]["items"]]
    if not states:
        reasons.append("no_check_evidence")
        return "unknown", reasons
    if reasons:
        states.append("unknown")
    result = next(state for state in STATES if state in states)
    reasons.append({"failure_observed": "current_head_failure_observed",
                    "pending_observed": "current_head_pending_observed",
                    "unknown": "current_head_check_evidence_incomplete_or_unknown",
                    "success_observed": "current_head_all_observed_checks_successful"}[result])
    return result, reasons


def summarize(snapshot: dict) -> dict:
    """Summarize a validated snapshot without time, config, I/O or mutation."""
    rows = []
    for source in sorted(snapshot["pull_requests"], key=lambda r: (r["repository"], r["number"])):
        state, reasons = _checks(source)
        mergeability = ("unknown" if source["mergeable"] is None else
                        "no_conflict_observed" if source["mergeable"] else "conflict")
        if mergeability == "conflict":
            reasons.append("merge_conflict_observed")
        elif mergeability == "unknown":
            reasons.append("mergeability_unknown")
        if source["draft"] is True:
            reasons.append("draft")
        elif source["draft"] is None:
            reasons.append("draft_state_unknown")
        base = f"https://github.com/{source['repository']}"
        rows.append({"repository": source["repository"], "number": source["number"],
                     "head_sha": source["head_sha"], "draft": source["draft"],
                     "mergeability": mergeability, "checks_state": state,
                     "reasons": reasons, "url": f"{base}/pull/{source['number']}",
                     "commit_url": f"{base}/commit/{source['head_sha']}",
                     "checks": deepcopy(source["checks"])})
    counts = Counter(row["checks_state"] for row in rows)
    return {"schema": "sigwood.repository-attention-report", "version": 1,
            "observed_at": snapshot["observed_at"],
            "repository_coverage": deepcopy(sorted(snapshot["repositories"], key=lambda r: r["repository"])),
            "totals": {"repositories": len(snapshot["repositories"]), "pull_requests": len(rows),
                       "checks_state": {state: counts[state] for state in STATES},
                       "conflicts": sum(r["mergeability"] == "conflict" for r in rows),
                       "drafts": sum(r["draft"] is True for r in rows),
                       "unknown_draft": sum(r["draft"] is None for r in rows)},
            "pull_requests": rows,
            "limitations": "Snapshot only; collection is not atomic and captured heads may have advanced. Supplied snapshots are unverified assertions; derived links do not prove repository or pull request existence. Required-check policy, reviews, owner holds and merge readiness not assessed."}
