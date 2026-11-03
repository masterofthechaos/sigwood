"""Offline, synthetic tests for the optional read-only GitHub collector."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import subprocess

import pytest

from tools import repository_snapshot as collector


REPO = "example/widget"
HEAD = "a" * 40
OTHER = "b" * 40
STAMP = "2026-01-01T00:00:00Z"


def pull(number=1, **kwargs):
    return {"number": number, "head": {"sha": HEAD}, "draft": False,
            "mergeable": True, "state": "open", **kwargs}


def run(identity=1, **kwargs):
    return {"id": identity, "head_sha": HEAD, "name": "tests",
            "status": "completed", "conclusion": "success", **kwargs}


class FakeGitHub:
    def __init__(self, pulls=None, runs=None, statuses=None):
        self.pulls = [pull()] if pulls is None else pulls
        self.runs = [run()] if runs is None else runs
        self.statuses = [] if statuses is None else statuses
        self.calls = []
        self.fail = set()
        self.details = {}

    def __call__(self, endpoint):
        self.calls.append(endpoint)
        if any(part in endpoint for part in self.fail):
            raise collector.CollectionError("unavailable")
        if "/pulls?" in endpoint:
            return deepcopy(self.pulls)
        if "/pulls/" in endpoint:
            number = int(endpoint.rsplit("/", 1)[1])
            return deepcopy(self.details.get(number, next(row for row in self.pulls if row["number"] == number)))
        if "/check-runs?" in endpoint:
            return {"total_count": len(self.runs), "check_runs": deepcopy(self.runs)}
        if "/statuses?" in endpoint:
            return deepcopy(self.statuses)
        raise AssertionError(endpoint)


def test_complete_snapshot_is_minimal_exact_head_and_deterministic():
    api = FakeGitHub()
    api.pulls[0].update(title="private text", body="secret", token="secret")
    result = collector.collect([REPO.upper(), REPO], api, STAMP)
    assert len(result) == 2
    assert result[0]["repositories"] == [{"repository": REPO, "pull_requests": "complete"}]
    assert result[1]["head_sha"] == result[1]["checks"]["head_sha"] == HEAD
    assert "secret" not in json.dumps(result)
    assert "private text" not in json.dumps(result)
    assert collector.collect([REPO], api, STAMP) == result
    assert all(call.startswith(f"repos/{REPO}/") for call in api.calls)
    assert any(f"commits/{HEAD}/check-runs?filter=latest&per_page=100&page=1" in call for call in api.calls)


@pytest.mark.parametrize("repositories", [[], ["../widget"], ["example/.."], ["example/./x"],
    ["https://github.com/example/widget"], ["example/widget?token=secret"], ["-owner/repo"],
    ["example/widget\n"], [None]])
def test_allowlist_validation_precedes_network(repositories):
    def fail(_):
        pytest.fail("network reached for invalid repository")
    with pytest.raises(collector.CollectionError):
        collector.collect(repositories, fail, STAMP)


def test_no_open_prs_distinguished_from_unavailable_repository():
    api = FakeGitHub(pulls=[])
    assert collector.collect([REPO], api, STAMP)[0]["repositories"][0]["pull_requests"] == "complete"
    api.fail = {"/pulls?"}
    result = collector.collect([REPO], api, STAMP)
    assert len(result) == 1
    assert result[0]["repositories"][0]["pull_requests"] == "unavailable"


def test_failed_details_preserve_listed_pr_with_unknown_mergeability_and_partial_coverage():
    api = FakeGitHub()
    api.fail = {"/pulls/1"}
    result = collector.collect([REPO], api, STAMP)
    assert result[1]["mergeable"] is None
    assert result[1]["head_sha"] == HEAD
    assert result[0]["repositories"][0]["pull_requests"] == "partial"


def test_closed_during_collection_not_reported_as_open_or_complete():
    api = FakeGitHub()
    api.details[1] = pull(state="closed")
    result = collector.collect([REPO], api, STAMP)
    assert len(result) == 1
    assert result[0]["repositories"][0]["pull_requests"] == "partial"


@pytest.mark.parametrize("bad", [None, "garbage", "a" * 39, True])
def test_invalid_head_not_invented(bad):
    result = collector.collect([REPO], FakeGitHub(pulls=[pull(head={"sha": bad})]), STAMP)
    assert len(result) == 1
    assert result[0]["repositories"][0]["pull_requests"] == "partial"


def test_each_run_head_checked_and_other_head_cannot_be_stamped_current():
    result = collector.collect([REPO], FakeGitHub(runs=[run(head_sha=OTHER)]), STAMP)
    assert result[1]["checks"]["check_runs"] == {"coverage": "partial", "items": []}


def test_duplicate_run_names_not_deduplicated_across_different_runs():
    api = FakeGitHub(runs=[run(1), run(2, conclusion="failure")])
    runs = collector.collect([REPO], api, STAMP)[1]["checks"]["check_runs"]
    assert [row["conclusion"] for row in runs["items"]] == ["success", "failure"]


def test_duplicate_run_id_marks_moving_collection_partial():
    api = FakeGitHub(runs=[run(1), run(1), run(1, conclusion="failure")])
    runs = collector.collect([REPO], api, STAMP)[1]["checks"]["check_runs"]
    assert runs["coverage"] == "partial"
    assert len(runs["items"]) == 2


def test_status_history_latest_per_case_insensitive_context():
    api = FakeGitHub(statuses=[{"context": "Build", "state": "success"},
                              {"context": "build", "state": "failure"},
                              {"context": "release", "state": "pending"}])
    states = collector.collect([REPO], api, STAMP)[1]["checks"]["statuses"]
    assert states == {"coverage": "complete", "items": [
        {"name": "Build", "state": "success"}, {"name": "release", "state": "pending"}]}


def test_malformed_latest_status_does_not_resurrect_older_success():
    api = FakeGitHub(statuses=[{"context": "Build", "state": None},
                              {"context": "build", "state": "success"}])
    assert collector.collect([REPO], api, STAMP)[1]["checks"]["statuses"] == {"coverage": "partial", "items": []}


@pytest.mark.parametrize("name", ["\x1b[31mtests", "test\nforged", "test\u202eabc", "x" * 257, ""])
def test_untrusted_check_names_cannot_escape_output(name):
    api = FakeGitHub(runs=[run(name=name)])
    assert collector.collect([REPO], api, STAMP)[1]["checks"]["check_runs"] == {"coverage": "partial", "items": []}


def test_missing_check_permission_is_unknown_coverage_not_empty_success():
    api = FakeGitHub()
    api.fail = {"/check-runs?"}
    checks = collector.collect([REPO], api, STAMP)[1]["checks"]
    assert checks["check_runs"] == {"coverage": "unavailable", "items": []}
    assert checks["statuses"] == {"coverage": "complete", "items": []}


def test_pagination_reaches_beyond_first_full_page():
    calls = []
    def get(endpoint):
        calls.append(endpoint)
        return list(range(100)) if endpoint.endswith("page=1") else [100]
    rows, coverage = collector._pages(get, "repos/example/widget/pulls?state=open")
    assert rows == list(range(101))
    assert coverage == "complete"
    assert len(calls) == 2


def test_pagination_failure_retains_known_rows_and_marks_partial():
    def get(endpoint):
        if endpoint.endswith("page=1"):
            return list(range(100))
        raise collector.CollectionError("unavailable")
    rows, coverage = collector._pages(get, "repos/example/widget/pulls")
    assert len(rows) == 100 and coverage == "partial"


def test_repeated_full_page_stops_without_claiming_complete():
    calls = []
    def get(endpoint):
        calls.append(endpoint)
        return list(range(100))
    rows, coverage = collector._pages(get, "repos/example/widget/pulls")
    assert len(rows) == 100 and len(calls) == 2 and coverage == "partial"


def test_pagination_cap_visible(monkeypatch):
    monkeypatch.setattr(collector, "_MAX_PAGES", 1)
    assert collector._pages(lambda _: list(range(100)), "repos/example/widget/pulls")[1] == "partial"


def test_check_total_disagreement_partial():
    rows, coverage = collector._pages(lambda _: {"total_count": 4, "check_runs": [run()]},
                                     "repos/example/widget/check-runs", "check_runs")
    assert len(rows) == 1 and coverage == "partial"


def test_gh_transport_fixed_host_get_no_shell_and_no_debug(monkeypatch):
    observed = {}
    def fake_run(argv, **kwargs):
        observed.update(argv=argv, kwargs=kwargs)
        return SimpleNamespace(returncode=0, stdout="[]", stderr="do not echo")
    monkeypatch.setattr(collector.subprocess, "run", fake_run)
    monkeypatch.setenv("GH_DEBUG", "api")
    assert collector.gh_get("repos/example/widget/pulls") == []
    assert observed["argv"][:7] == ["gh", "api", "--hostname", "github.com", "--method", "GET", "--header"]
    assert "shell" not in observed["kwargs"]
    assert "GH_DEBUG" not in observed["kwargs"]["env"]
    assert observed["kwargs"]["timeout"] == 60


@pytest.mark.parametrize("failure", ["exit", "json", "timeout", "missing"])
def test_gh_errors_do_not_echo_sensitive_response(monkeypatch, failure):
    def fake_run(*args, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired("private credential", 60)
        if failure == "missing":
            raise OSError("private credential")
        return SimpleNamespace(returncode=1 if failure == "exit" else 0,
                               stdout="private credential", stderr="private credential")
    monkeypatch.setattr(collector.subprocess, "run", fake_run)
    with pytest.raises(collector.CollectionError) as error:
        collector.gh_get("repos/example/widget/pulls")
    assert "private" not in str(error.value)


def test_main_emits_valid_partial_snapshot_and_nonzero_coverage_code(monkeypatch, capsys):
    api = FakeGitHub()
    api.fail = {"/check-runs?"}
    records = collector.collect([REPO], api, STAMP)
    monkeypatch.setattr(collector, "collect", lambda repos: records)
    assert collector.main([REPO]) == 2
    output = capsys.readouterr()
    assert [json.loads(line) for line in output.out.splitlines()] == records
    assert "incomplete coverage" in output.err


def test_main_complete_exit_zero(monkeypatch, capsys):
    records = collector.collect([REPO], FakeGitHub(), STAMP)
    monkeypatch.setattr(collector, "collect", lambda repos: records)
    assert collector.main([REPO]) == 0
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("args", [[], [REPO, "--unexpected-private-argument"]])
def test_main_usage_errors_have_no_artifact_and_distinct_code(args, capsys):
    assert collector.main(args) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "invalid arguments" in output.err
    assert "private-argument" not in output.err


def test_real_collector_process_to_real_analyzer_without_credentials_or_network(tmp_path):
    fake_gh = tmp_path / "gh"
    fake_gh.write_text(f"#!{sys.executable}\n" + '''
import json, sys
assert sys.argv[1:7] == ["api", "--hostname", "github.com", "--method", "GET", "--header"]
endpoint = sys.argv[-1]
head = "a" * 40
pull = {"number": 1, "state": "open", "head": {"sha": head}, "draft": False, "mergeable": True}
if endpoint == "repos/example/widget/pulls?state=open&sort=created&direction=asc&per_page=100&page=1":
    result = [pull]
elif endpoint == "repos/example/widget/pulls/1":
    result = pull
elif endpoint == f"repos/example/widget/commits/{head}/check-runs?filter=latest&per_page=100&page=1":
    result = {"total_count": 1, "check_runs": [{"id": 1, "head_sha": head, "name": "unit", "status": "completed", "conclusion": "success"}]}
elif endpoint == f"repos/example/widget/commits/{head}/statuses?per_page=100&page=1":
    result = []
else:
    raise AssertionError("unexpected endpoint")
print(json.dumps(result))
''', encoding="utf-8")
    fake_gh.chmod(0o700)
    root = Path(__file__).resolve().parents[1]
    # No inherited credentials; gh can only resolve to this synthetic executable.
    env = {"PATH": str(tmp_path), "HOME": str(tmp_path), "PYTHONPATH": str(root)}
    collected = subprocess.run(
        [sys.executable, str(root / "tools/repository_snapshot.py"), REPO],
        capture_output=True, text=True, timeout=30, cwd=tmp_path, env=env,
    )
    assert collected.returncode == 0, collected.stderr
    assert collected.stderr == ""
    snapshot = tmp_path / "captured.ndjson"
    snapshot.write_text(collected.stdout, encoding="utf-8")
    analyzed = subprocess.run(
        [sys.executable, "-m", "sigwood", "repos", str(snapshot), "--format=json"],
        capture_output=True, text=True, timeout=30, cwd=tmp_path, env=env,
    )
    assert analyzed.returncode == 0, analyzed.stderr
    report = json.loads(analyzed.stdout)
    assert report["totals"]["pull_requests"] == 1
    assert report["pull_requests"][0]["checks_state"] == "success_observed"
    assert report["pull_requests"][0]["head_sha"] == HEAD
