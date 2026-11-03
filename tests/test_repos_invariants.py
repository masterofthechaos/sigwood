"""Independent repository-attention invariants: no optimistic evidence inference."""
from __future__ import annotations

from copy import deepcopy
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from sigwood.repos import parse_snapshot, summarize, render_json, render_text

SHA = "a" * 40
OTHER_SHA = "b" * 40


def header():
    return {"schema": "sigwood.repository-attention", "version": 1, "type": "snapshot",
            "observed_at": "2026-01-01T00:00:00Z",
            "repositories": [{"repository": "example/widget", "pull_requests": "complete"}]}


def pr():
    return {"type": "pull_request", "repository": "example/widget", "number": 1,
            "head_sha": SHA, "draft": False, "mergeable": True,
            "checks": {"head_sha": SHA,
                       "check_runs": {"coverage": "complete", "items": [{"name": "unit", "status": "completed", "conclusion": "success"}]},
                       "statuses": {"coverage": "complete", "items": []}}}


def analyze(row=None, hdr=None):
    records = [hdr or header(), row or pr()]
    return summarize(parse_snapshot(json.dumps(record) + "\n" for record in records))


def check_state(row):
    return analyze(row)["pull_requests"][0]["checks_state"]


def test_reordering_repositories_prs_and_check_items_has_identical_report_bytes():
    hdr = header()
    hdr["repositories"].append({"repository": "example/second", "pull_requests": "partial"})
    one, two = pr(), pr()
    two.update(repository="example/second", number=8, draft=True)
    one["checks"]["check_runs"]["items"].append({"name": "lint", "status": "completed", "conclusion": "failure"})
    two["checks"]["statuses"]["items"] = [{"name": "z", "state": "pending"}, {"name": "a", "state": "error"}]
    original = summarize(parse_snapshot(map(json.dumps, [hdr, one, two])))
    hdr["repositories"].reverse()
    one["checks"]["check_runs"]["items"].reverse()
    two["checks"]["statuses"]["items"].reverse()
    reordered = summarize(parse_snapshot(map(json.dumps, [hdr, two, one])))
    assert render_json(original) == render_json(reordered)
    assert render_text(original) == render_text(reordered)


@pytest.mark.parametrize("coverage", ["partial", "unavailable"])
@pytest.mark.parametrize("lane", ["check_runs", "statuses"])
def test_coverage_gap_never_turns_observed_success_into_green(coverage, lane):
    row = pr()
    row["checks"][lane]["coverage"] = coverage
    if coverage == "unavailable":
        row["checks"][lane]["items"] = []
    assert check_state(row) == "unknown"


@pytest.mark.parametrize("evidence_head", [None, OTHER_SHA])
@pytest.mark.parametrize("conclusion", ["success", "failure", "cancelled", "timed_out"])
def test_stale_or_unattributed_checks_never_become_current_findings(evidence_head, conclusion):
    row = pr()
    row["checks"]["head_sha"] = evidence_head
    row["checks"]["check_runs"]["items"][0]["conclusion"] = conclusion
    report = analyze(row)
    result = report["pull_requests"][0]
    assert result["checks_state"] == "unknown"
    assert result["head_sha"] == SHA
    assert result["checks"]["head_sha"] == evidence_head
    assert result["reasons"]


@pytest.mark.parametrize("conclusion", [None, "neutral", "skipped", "future_outcome"])
def test_unproven_conclusions_never_count_as_success(conclusion):
    row = pr()
    row["checks"]["check_runs"]["items"][0]["conclusion"] = conclusion
    assert check_state(row) == "unknown"


def test_empty_check_apis_are_unknown_not_pending():
    row = pr()
    row["checks"]["check_runs"]["items"] = []
    assert check_state(row) == "unknown"


@pytest.mark.parametrize("unknown_status", ["future_status", "completed"])
def test_failure_precedes_pending_and_unknown_without_dropping_duplicate_names(unknown_status):
    row = pr()
    row["checks"]["check_runs"] = {"coverage": "partial", "items": [
        {"name": "same", "status": "completed", "conclusion": "failure"},
        {"name": "same", "status": "completed", "conclusion": "success"},
        {"name": "same", "status": "in_progress", "conclusion": None},
        {"name": "same", "status": unknown_status, "conclusion": None},
    ]}
    for items in itertools.permutations(row["checks"]["check_runs"]["items"]):
        row["checks"]["check_runs"]["items"] = list(items)
        assert check_state(row) == "failure_observed"


@pytest.mark.parametrize("mergeable, expected", [(None, "unknown"), (False, "conflict"), (True, "no_conflict_observed")])
def test_mergeability_remains_tristate_and_not_readiness(mergeable, expected):
    row = pr()
    row["mergeable"] = mergeable
    row["draft"] = True
    result = analyze(row)["pull_requests"][0]
    assert result["mergeability"] == expected
    assert result["draft"] is True
    assert result["checks_state"] == "success_observed"
    assert "ready" not in result["mergeability"]


@pytest.mark.parametrize("unsafe", ["\x1b[31mred", "safe\x00hidden", "safe\nforged", "safe\rforged", "safe\u0085forged", "safe\u202eforged", "safe\u2066forged", "safe\ud800", "safe\u2028forged", "safe\u2029forged"])
def test_untrusted_check_names_cannot_control_output_or_raise_encoding_errors(unsafe):
    row = pr()
    row["checks"]["check_runs"]["items"][0]["name"] = "PRIVATE_SENTINEL_" + unsafe
    with pytest.raises(ValueError) as failure:
        analyze(row)
    text = str(failure.value)
    assert "PRIVATE_SENTINEL" not in text
    assert "line 2" in text.lower()
    assert "\x1b" not in text
    text.encode("utf-8")


@pytest.mark.parametrize("location", ["header", "nested_head", "nested_coverage"])
def test_recursive_duplicate_json_keys_fail_closed(location):
    hdr, row = json.dumps(header()), json.dumps(pr())
    if location == "header":
        hdr = hdr.replace('"version": 1', '"version": 99, "version": 1')
    elif location == "nested_head":
        row = row.replace('"checks": {"head_sha":', '"checks": {"head_sha": "' + OTHER_SHA + '", "head_sha":')
    else:
        row = row.replace('"coverage": "complete"', '"coverage": "unavailable", "coverage": "complete"', 1)
    with pytest.raises(ValueError):
        parse_snapshot([hdr, row])


@pytest.mark.parametrize("field", ["version", "number"])
def test_booleans_are_not_schema_versions_or_pr_numbers(field):
    hdr, row = header(), pr()
    (hdr if field == "version" else row)[field] = True
    with pytest.raises(ValueError):
        analyze(row, hdr)


def test_malformed_nested_json_errors_do_not_echo_input_or_escape_as_recursionerror():
    payload = '{"PRIVATE_SENTINEL":' + '[' * 2000 + '0' + ']' * 2000 + '}'
    with pytest.raises(ValueError) as failure:
        parse_snapshot([payload])
    assert "PRIVATE_SENTINEL" not in str(failure.value)


def test_conflicting_duplicate_pr_cannot_overwrite_failure_with_success():
    failure, success = pr(), pr()
    failure["checks"]["check_runs"]["items"][0]["conclusion"] = "failure"
    for records in ([header(), failure, success], [header(), success, failure]):
        with pytest.raises(ValueError):
            parse_snapshot(map(json.dumps, records))


def test_unavailable_repository_cannot_hide_claimed_pr_rows():
    hdr = header()
    hdr["repositories"][0]["pull_requests"] = "unavailable"
    with pytest.raises(ValueError):
        analyze(pr(), hdr)


def test_core_does_not_mutate_validated_snapshot():
    snapshot = parse_snapshot(map(json.dumps, [header(), pr()]))
    before = deepcopy(snapshot)
    first = summarize(snapshot)
    render_text(first)
    render_json(first)
    assert snapshot == before
    assert first == summarize(snapshot)


def test_actual_cli_uses_no_network_processes_config_or_prompts(tmp_path):
    source = tmp_path / "snapshot.ndjson"
    source.write_text("\n".join(map(json.dumps, [header(), pr()])), encoding="utf-8")
    script = '''
import sys

def audit(event, args):
    if event in {"socket.connect", "socket.bind", "subprocess.Popen", "os.system"}:
        raise AssertionError("unexpected side effect: " + event)
sys.addaudithook(audit)
import builtins
import sigwood.cli as cli

def denied(*args, **kwargs):
    raise AssertionError("unexpected configuration, prompt, or output registry")
cli.cfg.load = denied
cli.get_handler = denied
builtins.input = denied
cli.main(sys.argv[1:])
'''
    result = subprocess.run([sys.executable, "-c", script, "repos", str(source), "--format", "json"],
                            capture_output=True, text=True, timeout=30, env=os.environ.copy())
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report["schema"] == "sigwood.repository-attention-report"
    assert report["pull_requests"][0]["checks_state"] == "success_observed"
    assert str(source) not in result.stdout


def _collector():
    """Load the opt-in script without making it part of analyzer imports."""
    import importlib.util
    import sigwood
    path = Path(sigwood.__file__).resolve().parent.parent / "tools" / "repository_snapshot.py"
    spec = importlib.util.spec_from_file_location("repository_snapshot_invariant_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("repository", ["owner-/repo", "example/...", "example/..", "example/repo?evil"])
def test_collector_rejects_schema_incompatible_repository_before_transport(repository):
    collector = _collector()
    calls = []
    with pytest.raises(collector.CollectionError):
        collector.collect([repository], get=lambda endpoint: calls.append(endpoint))
    assert calls == []


def _fake_transport(*, check_name="unit", detail_number=1):
    def get(endpoint):
        if "/pulls?" in endpoint:
            return [{"number": 1, "head": {"sha": SHA}, "draft": False}]
        if endpoint.endswith("/pulls/1"):
            return {"number": detail_number, "state": "open", "head": {"sha": SHA}, "draft": False, "mergeable": True}
        if "/check-runs?" in endpoint:
            return {"total_count": 1, "check_runs": [{"id": 1, "head_sha": SHA, "name": check_name, "status": "completed", "conclusion": "success", "check_suite": {"id": 1}}]}
        if "/statuses?" in endpoint:
            return []
        raise AssertionError("unexpected endpoint")
    return get


def test_collector_whitespace_check_name_becomes_gap_not_invalid_snapshot():
    collector = _collector()
    records = collector.collect(["example/widget"], get=_fake_transport(check_name="   "), observed_at="2026-01-01T00:00:00Z")
    report = summarize(parse_snapshot(map(json.dumps, records)))
    assert report["pull_requests"][0]["checks_state"] == "unknown"
    assert report["pull_requests"][0]["checks"]["check_runs"]["coverage"] == "partial"


def test_collector_bool_detail_identity_cannot_establish_mergeability():
    collector = _collector()
    records = collector.collect(["example/widget"], get=_fake_transport(detail_number=True), observed_at="2026-01-01T00:00:00Z")
    report = summarize(parse_snapshot(map(json.dumps, records)))
    assert report["repository_coverage"][0]["pull_requests"] == "partial"
    assert report["pull_requests"][0]["mergeability"] == "unknown"
