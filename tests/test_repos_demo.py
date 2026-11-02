"""The shipped example is synthetic, deterministic and usable end to end."""
from pathlib import Path
import json

import pytest

from sigwood import cli
from sigwood.repos import parse_snapshot, summarize, render_json, render_text


ROOT = Path(__file__).resolve().parents[1]


def test_demo_matches_reviewed_text_and_json_goldens():
    with (ROOT / "demo/repository-attention.ndjson").open(encoding="utf-8") as source:
        report = summarize(parse_snapshot(source))
    assert report["totals"]["pull_requests"] == 3
    assert report["totals"]["conflicts"] == 1
    assert report["totals"]["drafts"] == 1
    assert report["totals"]["checks_state"] == {
        "failure_observed": 1, "pending_observed": 0, "unknown": 1, "success_observed": 1,
    }
    for name, result in [("txt", render_text(report)), ("json", render_json(report))]:
        assert result == (ROOT / f"tests/fixtures/repository-attention-report.{name}").read_text(encoding="utf-8")


def test_demo_cli_outputs_valid_json(capsys):
    assert cli._main(["repos", str(ROOT / "demo/repository-attention.ndjson"), "--format", "json"]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert json.loads(output.out)["totals"]["pull_requests"] == 3


def test_oversized_utf8_line_is_reported_as_size_error_not_broken_encoding(tmp_path):
    source = tmp_path / "huge.ndjson"
    source.write_bytes(b" " * ((1 << 20) - 1) + "\u20ac".encode("utf-8"))
    with pytest.raises(ValueError, match="1 MiB"):
        cli._main(["repos", str(source)])
