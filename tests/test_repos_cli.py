"""Offline repo-attention CLI contracts; no credentials or user snapshots."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

from sigwood import cli


@pytest.fixture
def no_other_paths(monkeypatch: pytest.MonkeyPatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("repos must not use config, sniff, detectors, registry, or prompts")
    for name in ("_load_config", "_run_hunt", "_run_digest", "_run_graph", "_run_export", "get_handler"):
        monkeypatch.setattr(cli, name, forbidden)
    monkeypatch.setattr(cli.cfg, "load", forbidden)
    monkeypatch.setattr(cli.cfg, "_find_config_file", forbidden)
    monkeypatch.setattr("builtins.input", forbidden)


@pytest.fixture
def fake_core(monkeypatch: pytest.MonkeyPatch):
    core = ModuleType("sigwood.repos")
    seen = []
    def parse(lines):
        captured = list(lines)
        seen.append(captured)
        return {"lines": len(captured)}
    core.parse_snapshot = parse
    core.summarize = lambda snapshot: {"known_records": snapshot["lines"]}
    core.render_json = lambda report: json.dumps(report, sort_keys=True)
    core.render_text = lambda report: "snapshot only\n"
    monkeypatch.setitem(sys.modules, "sigwood.repos", core)
    return core, seen


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_repos_help_has_only_applicable_flags(flag, no_other_paths, capsys):
    assert cli._main(["repos", flag]) == 0
    output = capsys.readouterr().out
    assert "Usage: sigwood repos [options] PATH" in output
    assert "experimental" in output
    assert "text or json; stdout only" in output
    assert "merge readiness is not assessed" in output
    for forbidden in ("--config", "--out", "--yes", "csv", "pdf", "--verbose"):
        assert forbidden not in output
    assert "sigwood repos" in cli._global_usage_text()


@pytest.mark.parametrize("args", [[], ["-"], ["one", "two"]])
def test_repos_requires_one_explicit_file(args, no_other_paths):
    with pytest.raises(cli.UsageError, match="exactly one local snapshot file"):
        cli._main(["repos", *args])


@pytest.mark.parametrize("flag", [
    "--config=secret", "--out=output", "--yes", "--all", "--quiet", "--dry-run",
    "--verbose", "--since=1d", "--detect=dns", "--zeek-dir=logs", "--version", "--bogus",
])
def test_repos_rejects_unrelated_flags(flag, no_other_paths):
    with pytest.raises(cli.UsageError):
        cli._main(["repos", "snapshot", flag])


@pytest.mark.parametrize("fmt", ["csv", "html", "pdf", "", "SECRET_PAYLOAD"])
def test_repos_rejects_unsupported_format_without_echoing_value(fmt, no_other_paths):
    with pytest.raises(cli.UsageError, match="supports only") as error:
        cli._main(["repos", "snapshot", f"--format={fmt}"])
    assert "SECRET_PAYLOAD" not in str(error.value)


@pytest.mark.parametrize("flags", [
    ["--format=json"], ["--format", "json"], ["-f=json"], ["-f", "json"],
])
def test_repos_json_formats_stream_read_only(tmp_path, flags, fake_core, no_other_paths, capsys):
    snapshot = tmp_path / "snapshot.ndjson"
    snapshot.write_text("first\nsecond\n", encoding="utf-8")
    before = snapshot.read_bytes()
    assert cli._main(["repos", str(snapshot), *flags]) == 0
    output = capsys.readouterr()
    assert output.out == '{"known_records": 2}\n'
    assert output.err == ""
    assert fake_core[1] == [["first\n", "second\n"]]
    assert snapshot.read_bytes() == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["snapshot.ndjson"]


def test_repos_text_default_no_duplicate_newline(tmp_path, fake_core, no_other_paths, capsys):
    snapshot = tmp_path / "snapshot.ndjson"
    snapshot.write_text("record\n", encoding="utf-8")
    assert cli._main(["repos", str(snapshot)]) == 0
    assert capsys.readouterr().out == "snapshot only\n"


def test_repos_nonexistent_file_error_redacts_path(tmp_path, no_other_paths, capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["repos", str(tmp_path / "PRIVATE_NAME")])
    assert error.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "sigwood: repos: snapshot file not found\n"
    assert "PRIVATE_NAME" not in output.err


def test_repos_directory_not_opened_as_snapshot(tmp_path, fake_core, no_other_paths):
    with pytest.raises(ValueError, match="regular local snapshot file"):
        cli._main(["repos", str(tmp_path)])
    assert fake_core[1] == []


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO required")
def test_repos_fifo_rejected_without_waiting_for_writer(tmp_path, fake_core, no_other_paths):
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="regular local snapshot file"):
        cli._main(["repos", str(fifo)])
    assert fake_core[1] == []


def test_repos_invalid_utf8_has_fixed_error(tmp_path, fake_core, no_other_paths, capsys):
    snapshot = tmp_path / "PRIVATE_NAME"
    snapshot.write_bytes(b"PRIVATE_CONTENT\xff\xfe\n")
    with pytest.raises(SystemExit) as error:
        cli.main(["repos", str(snapshot)])
    assert error.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "sigwood: line 1: snapshot must be UTF-8 text\n"


def test_repos_parser_error_has_no_partial_output(tmp_path, fake_core, no_other_paths, capsys):
    snapshot = tmp_path / "snapshot"
    snapshot.write_text("PRIVATE_CONTENT\n", encoding="utf-8")
    def reject(lines):
        raise ValueError("line 1: invalid snapshot header")
    fake_core[0].parse_snapshot = reject
    with pytest.raises(SystemExit) as error:
        cli.main(["repos", str(snapshot)])
    assert error.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "sigwood: line 1: invalid snapshot header\n"


def test_repos_bounds_reads_before_parser(tmp_path, fake_core, no_other_paths):
    snapshot = tmp_path / "snapshot"
    snapshot.write_text("x" * ((1 << 20) * 3), encoding="utf-8")
    def reject(lines):
        line = next(iter(lines))
        assert len(line) == (1 << 20) + 1
        raise ValueError("line 1: line exceeds limit")
    fake_core[0].parse_snapshot = reject
    with pytest.raises(ValueError, match="line exceeds limit"):
        cli._main(["repos", str(snapshot)])



def test_repos_rejects_oversized_file_before_parsing(tmp_path, fake_core, no_other_paths):
    snapshot = tmp_path / "snapshot"
    with snapshot.open("wb") as stream:
        stream.truncate((64 << 20) + 1)
    with pytest.raises(ValueError, match="64 MiB input limit"):
        cli._main(["repos", str(snapshot)])
    assert fake_core[1] == []

def test_real_empty_snapshot_error(tmp_path, no_other_paths, capsys):
    snapshot = tmp_path / "empty"
    snapshot.write_text("\n", encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        cli.main(["repos", str(snapshot)])
    assert error.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "sigwood:" in output.err
    assert "Traceback" not in output.err


@pytest.mark.parametrize("contents", ["{\"SECRET\":", '{"schema":"invalid","version":1}\n'])
def test_real_malformed_schema_redacts_payload(tmp_path, contents, no_other_paths, capsys):
    snapshot = tmp_path / "invalid"
    snapshot.write_text(contents, encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        cli.main(["repos", str(snapshot), "--format", "json"])
    assert error.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "SECRET" not in output.err
    assert "line 1" in output.err.lower()


def test_real_header_only_snapshot_is_valid_and_deterministic(tmp_path, no_other_paths, capsys):
    snapshot = tmp_path / "snapshot"
    header = {"schema": "sigwood.repository-attention", "version": 1, "type": "snapshot",
              "observed_at": "2026-01-01T00:00:00Z",
              "repositories": [{"repository": "example/widget", "pull_requests": "complete"}]}
    snapshot.write_text(json.dumps(header) + "\n", encoding="utf-8")
    for _ in range(2):
        assert cli._main(["repos", str(snapshot), "--format=json"]) == 0
        output = capsys.readouterr()
        parsed = json.loads(output.out)
        assert parsed["schema"] == "sigwood.repository-attention-report"
        assert output.err == ""
        if _ == 0:
            first = output.out
        else:
            assert output.out == first


@pytest.mark.parametrize("check_head,conclusion,expected", [
    ("a" * 40, "failure", "failure_observed"),
    ("a" * 40, "success", "success_observed"),
    ("b" * 40, "success", "unknown"),
])
def test_real_pr_snapshot_retains_exact_head_provenance(
    tmp_path, check_head, conclusion, expected, no_other_paths, capsys,
):
    snapshot = tmp_path / "snapshot"
    header = {"schema": "sigwood.repository-attention", "version": 1, "type": "snapshot",
              "observed_at": "2026-01-01T00:00:00Z",
              "repositories": [{"repository": "example/widget", "pull_requests": "complete"}]}
    row = {"type": "pull_request", "repository": "example/widget", "number": 7,
           "head_sha": "a" * 40, "draft": True, "mergeable": None,
           "checks": {"head_sha": check_head,
                      "check_runs": {"coverage": "complete", "items": [
                          {"name": "tests", "status": "completed", "conclusion": conclusion}]},
                      "statuses": {"coverage": "complete", "items": []}}}
    snapshot.write_text(json.dumps(header) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    assert cli._main(["repos", str(snapshot), "--format=json"]) == 0
    report = json.loads(capsys.readouterr().out)
    pr = report["pull_requests"][0]
    assert pr["checks_state"] == expected
    assert pr["draft"] is True
    assert pr["head_sha"] == "a" * 40
    assert pr["checks"]["head_sha"] == check_head
    assert pr["commit_url"] == "https://github.com/example/widget/commit/" + "a" * 40
    assert cli._main(["repos", str(snapshot)]) == 0
    output = capsys.readouterr()
    assert expected in output.out
    assert "merge readiness not assessed" in output.out
    assert output.err == ""
