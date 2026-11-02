"""Plain, deterministic output for repository observations, separate from hunts."""
from __future__ import annotations

import json


def render_json(report: dict) -> str:
    return json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def render_text(report: dict) -> str:
    totals = report["totals"]
    lines = ["Repository attention snapshot", f"Observed at: {report['observed_at']}",
             f"Listed repositories: {totals['repositories']} | Known pull requests: {totals['pull_requests']}",
             "Observed check states: " + " | ".join(
                 f"{state}: {totals['checks_state'][state]}" for state in
                 ("failure_observed", "pending_observed", "unknown", "success_observed")),
             f"Conflicts observed: {totals['conflicts']} | Drafts: {totals['drafts']} | Draft state unknown: {totals['unknown_draft']}",
             "Repository pull-request coverage:"]
    for repository in report["repository_coverage"]:
        lines.append(f"  {repository['repository']}: {repository['pull_requests']}")
    for row in report["pull_requests"]:
        draft = "unknown" if row["draft"] is None else str(row["draft"]).lower()
        lines.extend(["", f"{row['repository']} #{row['number']}",
                      f"  Head: {row['head_sha']}", f"  PR: {row['url']}",
                      f"  Commit: {row['commit_url']}",
                      f"  Draft: {draft} | Mergeability: {row['mergeability']}",
                      f"  Checks: {row['checks_state']}",
                      f"  Check evidence head: {row['checks']['head_sha'] or 'unknown'}",
                      f"  Reasons: {', '.join(row['reasons'])}"])
        for kind in ("check_runs", "statuses"):
            group = row["checks"][kind]
            lines.append(f"  {kind} coverage: {group['coverage']}")
            for item in group["items"]:
                detail = (f"{item['status']} / {item['conclusion'] or 'unknown'}" if kind == "check_runs"
                          else item["state"])
                lines.append(f"    {item['name']}: {detail}")
    lines.extend(["", report["limitations"]])
    return "\n".join(lines) + "\n"
