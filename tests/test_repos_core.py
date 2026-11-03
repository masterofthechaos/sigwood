"""Synthetic-only, offline contract and policy tests for repository attention."""
from copy import deepcopy
import json
import pytest
from sigwood.repos import parse_snapshot, summarize, render_json, render_text
from sigwood.repos import schema

SHA = "a" * 40
OTHER = "b" * 40


def header(coverage="complete", repo="example/widget"):
    return {"schema": "sigwood.repository-attention", "version": 1, "type": "snapshot",
            "observed_at": "2026-01-01T00:00:00Z", "repositories": [
                {"repository": repo, "pull_requests": coverage}]}


def pr(**overrides):
    value = {"type": "pull_request", "repository": "example/widget", "number": 1,
             "head_sha": SHA, "draft": False, "mergeable": None,
             "checks": {"head_sha": SHA,
                        "check_runs": {"coverage": "complete", "items": [run()]},
                        "statuses": {"coverage": "complete", "items": []}}}
    value.update(overrides)
    return value


def run(status="completed", conclusion="success", name="tests"):
    return {"name": name, "status": status, "conclusion": conclusion}


def parse(*rows):
    return parse_snapshot([json.dumps(r) for r in rows])


def report(row=None, h=None):
    return summarize(parse(h or header(), row or pr()))


def state(row):
    return report(row)["pull_requests"][0]["checks_state"]


def test_success_is_observation_not_readiness():
    value = report()
    assert value["schema"] == "sigwood.repository-attention-report"
    assert value["version"] == 1
    row = value["pull_requests"][0]
    assert row["checks_state"] == "success_observed"
    assert row["mergeability"] == "unknown"
    assert row["url"] == "https://github.com/example/widget/pull/1"
    assert row["commit_url"] == f"https://github.com/example/widget/commit/{SHA}"
    assert "merge readiness not assessed" in render_text(value)
    assert "not atomic" in render_text(value)
    assert "may have advanced" in render_text(value)
    assert "Supplied snapshots are unverified assertions" in render_text(value)
    assert "derived links do not prove" in render_text(value)
    assert "success_observed: 1" in render_text(value)
    assert "failure_observed: 0" in render_text(value)
    assert "Conflicts observed: 0 | Drafts: 0" in render_text(value)
    assert "CI passed" not in render_text(value)
    assert "ready-to-merge" not in render_text(value)


@pytest.mark.parametrize("conclusion", ["failure", "timed_out", "cancelled", "action_required", "startup_failure", "stale"])
def test_completed_run_failure(conclusion):
    row = pr()
    row["checks"]["check_runs"]["items"] = [run(conclusion=conclusion)]
    assert state(row) == "failure_observed"


@pytest.mark.parametrize("status", ["queued", "in_progress", "waiting", "pending", "requested"])
def test_pending_run(status):
    row = pr()
    row["checks"]["check_runs"]["items"] = [run(status=status, conclusion=None)]
    assert state(row) == "pending_observed"


@pytest.mark.parametrize("conclusion", [None, "neutral", "skipped", "future", "SUCCESS"])
def test_other_conclusions_are_unknown(conclusion):
    row = pr()
    row["checks"]["check_runs"]["items"] = [run(conclusion=conclusion)]
    assert state(row) == "unknown"


@pytest.mark.parametrize("status,expected", [("failure", "failure_observed"), ("error", "failure_observed"), ("pending", "pending_observed"), ("success", "success_observed"), ("future", "unknown")])
def test_legacy_status(status, expected):
    row = pr()
    row["checks"]["check_runs"]["items"] = []
    row["checks"]["statuses"]["items"] = [{"name": "legacy-tests", "state": status}]
    assert state(row) == expected


def test_failure_precedes_pending_unknown_and_success():
    row = pr()
    row["checks"]["check_runs"]["items"] = [run(conclusion="skipped"), run("waiting", None), run(conclusion="failure"), run()]
    row["checks"]["statuses"]["coverage"] = "unavailable"
    assert state(row) == "failure_observed"
    assert "statuses_coverage_unavailable" in report(row)["pull_requests"][0]["reasons"]


def test_pending_precedes_unknown_and_partial_coverage():
    row = pr()
    row["checks"]["check_runs"]["items"] = [run(conclusion="neutral"), run("in_progress", None)]
    row["checks"]["check_runs"]["coverage"] = "partial"
    assert state(row) == "pending_observed"


@pytest.mark.parametrize("head,reason", [(None, "missing_check_head"), (OTHER, "stale_check_head")])
@pytest.mark.parametrize("conclusion", ["success", "failure"])
def test_old_or_missing_head_never_becomes_current(head, reason, conclusion):
    row = pr()
    row["checks"]["head_sha"] = head
    row["checks"]["check_runs"]["items"] = [run(conclusion=conclusion)]
    result = report(row)["pull_requests"][0]
    assert result["checks_state"] == "unknown"
    assert reason in result["reasons"]
    assert result["checks"]["head_sha"] == head
    assert result["checks"]["check_runs"]["items"][0]["conclusion"] == conclusion


@pytest.mark.parametrize("api", ["check_runs", "statuses"])
@pytest.mark.parametrize("coverage", ["partial", "unavailable"])
def test_partial_api_prevents_success(api, coverage):
    row = pr()
    row["checks"][api]["coverage"] = coverage
    if coverage == "unavailable":
        row["checks"][api]["items"] = []
    assert state(row) == "unknown"


def test_empty_checks_are_unknown_not_pending():
    row = pr()
    row["checks"]["check_runs"]["items"] = []
    result = report(row)["pull_requests"][0]
    assert result["checks_state"] == "unknown"
    assert "no_check_evidence" in result["reasons"]


@pytest.mark.parametrize("mergeable,expected", [(False, "conflict"), (True, "no_conflict_observed"), (None, "unknown")])
@pytest.mark.parametrize("draft", [True, False, None])
def test_drafts_and_conflicts_are_separate(mergeable, expected, draft):
    result = report(pr(mergeable=mergeable, draft=draft))["pull_requests"][0]
    assert result["mergeability"] == expected
    assert result["draft"] is draft
    assert result["checks_state"] == "success_observed"


def test_empty_partial_and_unavailable_repositories_are_visible():
    h = header("partial")
    h["repositories"].append({"repository": "example/other", "pull_requests": "unavailable"})
    result = summarize(parse(h))
    assert result["totals"]["pull_requests"] == 0
    assert result["totals"]["repositories"] == 2
    assert "example/other: unavailable" in render_text(result)
    assert "Known pull requests: 0" in render_text(result)


def test_identical_pr_duplicates_and_check_duplicates_do_not_inflate_counts():
    row = pr()
    repeated = deepcopy(row)
    repeated["checks"]["check_runs"]["items"] *= 3
    result = summarize(parse(header(), row, repeated))
    assert result["totals"]["pull_requests"] == 1
    assert len(result["pull_requests"][0]["checks"]["check_runs"]["items"]) == 1


def test_conflicting_pr_duplicates_are_rejected():
    with pytest.raises(ValueError, match="line 3: contradictory duplicate pull request"):
        parse(header(), pr(), pr(head_sha=OTHER))


def test_deterministic_permutation_normalizes_heads_repos_and_time():
    h = header(repo="EXAMPLE/WIDGET")
    h["observed_at"] = "2025-12-31T19:00:00-05:00"
    first, second = pr(number=2, head_sha=SHA.upper()), pr(number=1)
    first["checks"]["check_runs"]["items"] = [run(name="z"), run(name="a")]
    reverse = deepcopy(first)
    reverse["checks"]["check_runs"]["items"].reverse()
    a = render_json(summarize(parse(h, first, second)))
    b = render_json(summarize(parse(header(), second, reverse)))
    assert a == b
    assert json.loads(a)["observed_at"] == "2026-01-01T00:00:00Z"


def test_no_mutation():
    source = parse(header(), pr())
    before = deepcopy(source)
    result = summarize(source)
    assert source == before
    result["pull_requests"][0]["checks"]["check_runs"]["items"].clear()
    assert source == before


@pytest.mark.parametrize("raw", ["", " \n\n", "[]", "null", "42", "true", "{", '{"schema": NaN}', "[" * 2000])
def test_empty_malformed_and_nonobject_are_fixed_errors(raw):
    with pytest.raises(ValueError, match=r"line \d+: "):
        parse_snapshot(raw.splitlines())


@pytest.mark.parametrize("field,value", [("version", True), ("version", 2), ("schema", "other"), ("repositories", []), ("observed_at", "2026-01-01T00:00:00"), ("observed_at", "secret-sensitive-value")])
def test_invalid_headers_redact_values(field, value):
    h = header()
    h[field] = value
    with pytest.raises(ValueError) as exc:
        parse(h)
    assert "secret-sensitive-value" not in str(exc.value)


@pytest.mark.parametrize("repo", ["../widget", "example/..", "example/...", "example/a/b", "https://github.com/example/widget", "example/a?token=secret", "example/a\nb", "example/a\u202eb", "example/☃"])
def test_repository_paths_are_safe(repo):
    with pytest.raises(ValueError, match="invalid repository identity"):
        parse(header(repo=repo))


@pytest.mark.parametrize("field,value", [("number", True), ("number", 0), ("number", -1), ("number", 1.0), ("draft", 1), ("mergeable", "true"), ("head_sha", "a" * 39), ("head_sha", "g" * 40), ("head_sha", None)])
def test_invalid_pr_primitives(field, value):
    with pytest.raises(ValueError):
        parse(header(), pr(**{field: value}))


def test_undeclared_and_unavailable_repositories_cannot_have_rows():
    with pytest.raises(ValueError, match="not declared"):
        parse(header(), pr(repository="example/other"))
    with pytest.raises(ValueError, match="unavailable repository"):
        parse(header("unavailable"), pr())


def test_duplicate_header_repo_aliases_rejected():
    h = header()
    h["repositories"].append({"repository": "EXAMPLE/Widget", "pull_requests": "complete"})
    with pytest.raises(ValueError, match="duplicate repository"):
        parse(h)


@pytest.mark.parametrize("field", ["title", "body", "url"])
def test_unknown_pr_fields_rejected(field):
    row = pr()
    row[field] = "secret-value"
    with pytest.raises(ValueError, match="invalid pull request fields") as exc:
        parse(header(), row)
    assert "secret-value" not in str(exc.value)


@pytest.mark.parametrize("name", ["", " ", "a" * 257, "secret\nvalue", "secret\x1bvalue", "secret\u202evalue", "secret\u2066value", "secret\u2028value", "secret\u2029value", "secret\ud800value", 123])
def test_unsafe_check_names_are_rejected_without_leaking(name):
    row = pr()
    row["checks"]["check_runs"]["items"] = [run(name=name)]
    with pytest.raises(ValueError, match="invalid check name") as exc:
        parse(header(), row)
    assert "secret" not in str(exc.value)


def test_unknown_enums_remain_unknown():
    row = pr()
    row["checks"]["check_runs"]["items"] = [run(status="future-state", conclusion="success")]
    assert state(row) == "unknown"


def test_nested_duplicate_json_keys_rejected():
    raw = json.dumps(pr()).replace('"status": "completed"', '"status": "completed", "status": "pending"')
    with pytest.raises(ValueError, match="line 2: duplicate JSON object key"):
        parse_snapshot([json.dumps(header()), raw])


def test_unavailable_check_items_contradiction():
    row = pr()
    row["checks"]["check_runs"]["coverage"] = "unavailable"
    with pytest.raises(ValueError, match="unavailable check coverage cannot contain items"):
        parse(header(), row)


def test_no_second_header_or_mixed_schema():
    with pytest.raises(ValueError, match="invalid pull request fields"):
        parse(header(), header())
    row = pr()
    row["schema"] = "foreign"
    with pytest.raises(ValueError, match="invalid pull request fields"):
        parse(header(), row)


def test_line_limit_and_total_limit_include_blank_lines(monkeypatch):
    with pytest.raises(ValueError, match="1 MiB"):
        parse_snapshot([" " * (schema.MAX_LINE_BYTES + 1)])
    monkeypatch.setattr(schema, "MAX_TOTAL_BYTES", 10)
    with pytest.raises(ValueError, match="64 MiB"):
        parse_snapshot([" " * 6, " " * 5])


def test_record_limit_counts_duplicate_rows(monkeypatch):
    monkeypatch.setattr(schema, "MAX_RECORDS", 1)
    with pytest.raises(ValueError, match="record limit"):
        parse(header(), pr(), pr())


def test_invalid_encoding_and_nontext_are_fixed():
    for value in [b"secret", "\ud800"]:
        with pytest.raises(ValueError, match="UTF-8") as exc:
            parse_snapshot([value])
        assert "secret" not in str(exc.value)


def test_large_json_integer_error_fixed_and_payload_free():
    with pytest.raises(ValueError, match="line 1: malformed JSON record"):
        parse_snapshot(["9" * 5000])


def test_json_output_is_ascii_sorted_roundtrippable():
    row = pr()
    row["checks"]["check_runs"]["items"][0]["name"] = "tésts"
    value = report(row)
    output = render_json(value)
    assert output.isascii()
    assert output == json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    assert json.loads(output) == value
