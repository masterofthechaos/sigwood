"""Strict, pure parsing for bounded repository-attention NDJSON snapshots."""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Iterable

SCHEMA = "sigwood.repository-attention"
MAX_LINE_BYTES = 1024 * 1024
MAX_RECORDS = 100000
MAX_TOTAL_BYTES = 64 * 1024 * 1024
_COVERAGE = {"complete", "partial", "unavailable"}
_OWNER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?\Z")
_REPO = re.compile(r"[A-Za-z0-9_.-]{1,100}\Z")
_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")


class _ValidationError(ValueError):
    """Internal fixed-message error, never a provider or JSON error."""


def _fail(reason: str) -> None:
    raise _ValidationError(reason)


def _object(value, keys: set[str], reason: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        _fail(reason)
    return value


def _string(value, reason: str, limit: int = 256) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(unicodedata.category(c) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for c in value)):
        _fail(reason)
    return value


def _repository(value) -> str:
    value = _string(value, "invalid repository identity")
    parts = value.split("/")
    if (len(parts) != 2 or not _OWNER.fullmatch(parts[0])
            or not _REPO.fullmatch(parts[1]) or not parts[1].strip(".")):
        _fail("invalid repository identity")
    return value.lower()


def _sha(value, nullable=False):
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        _fail("invalid head SHA")
    return value.lower()


def _coverage(value) -> str:
    if not isinstance(value, str) or value not in _COVERAGE:
        _fail("invalid coverage")
    return value


def _nullable_bool(value):
    if value is not None and type(value) is not bool:
        _fail("invalid boolean or null field")
    return value


def _observed_at(value) -> str:
    value = _string(value, "invalid observed_at timestamp", 64)
    if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", value):
        _fail("invalid observed_at timestamp")
    try:
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            _fail("invalid observed_at timestamp")
        return stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError):
        _fail("invalid observed_at timestamp")


def _header(record) -> dict:
    _object(record, {"schema", "version", "type", "observed_at", "repositories"}, "invalid snapshot header fields")
    if record["schema"] != SCHEMA or type(record["version"]) is not int or record["version"] != 1:
        _fail("unsupported snapshot schema or version")
    if record["type"] != "snapshot":
        _fail("first record must be snapshot header")
    repositories = record["repositories"]
    if not isinstance(repositories, list) or not repositories:
        _fail("repository coverage list must be nonempty")
    result, seen = [], set()
    for item in repositories:
        _object(item, {"repository", "pull_requests"}, "invalid repository coverage fields")
        repository = _repository(item["repository"])
        if repository in seen:
            _fail("duplicate repository coverage")
        seen.add(repository)
        result.append({"repository": repository, "pull_requests": _coverage(item["pull_requests"])})
    return {"schema": SCHEMA, "version": 1, "observed_at": _observed_at(record["observed_at"]),
            "repositories": sorted(result, key=lambda r: r["repository"])}


def _check_group(value, runs: bool) -> dict:
    _object(value, {"coverage", "items"}, "invalid check coverage fields")
    coverage = _coverage(value["coverage"])
    if not isinstance(value["items"], list):
        _fail("check items must be a list")
    if coverage == "unavailable" and value["items"]:
        _fail("unavailable check coverage cannot contain items")
    items = []
    for item in value["items"]:
        keys = {"name", "status", "conclusion"} if runs else {"name", "state"}
        _object(item, keys, "invalid check item fields")
        row = {"name": _string(item["name"], "invalid check name")}
        if runs:
            row["status"] = _string(item["status"], "invalid check status")
            row["conclusion"] = (None if item["conclusion"] is None else
                                 _string(item["conclusion"], "invalid check conclusion"))
        else:
            row["state"] = _string(item["state"], "invalid legacy status")
        items.append(row)
    items.sort(key=lambda r: (r["name"], r.get("status", r.get("state", "")), r.get("conclusion") or ""))
    unique = []
    for item in items:
        if not unique or item != unique[-1]:
            unique.append(item)
    return {"coverage": coverage, "items": unique}


def _pull_request(record, coverage: dict[str, str]) -> dict:
    _object(record, {"type", "repository", "number", "head_sha", "draft", "mergeable", "checks"}, "invalid pull request fields")
    if record["type"] != "pull_request":
        _fail("expected pull_request record")
    repository = _repository(record["repository"])
    if repository not in coverage:
        _fail("pull request repository not declared")
    if coverage[repository] == "unavailable":
        _fail("unavailable repository coverage cannot contain pull requests")
    number = record["number"]
    if type(number) is not int or number <= 0:
        _fail("invalid pull request number")
    checks = _object(record["checks"], {"head_sha", "check_runs", "statuses"}, "invalid checks fields")
    return {"type": "pull_request", "repository": repository, "number": number,
            "head_sha": _sha(record["head_sha"]), "draft": _nullable_bool(record["draft"]),
            "mergeable": _nullable_bool(record["mergeable"]),
            "checks": {"head_sha": _sha(checks["head_sha"], nullable=True),
                       "check_runs": _check_group(checks["check_runs"], True),
                       "statuses": _check_group(checks["statuses"], False)}}


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate JSON object key")
        result[key] = value
    return result


def parse_snapshot(lines: Iterable[str]) -> dict:
    """Validate all evidence before returning; errors never include input values."""
    snapshot, coverage, rows = None, {}, {}
    record_count = 0
    total_bytes = 0
    for line_number, line in enumerate(lines, 1):
        try:
            if not isinstance(line, str):
                _fail("input must be UTF-8 text")
            try:
                size = len(line.encode("utf-8"))
            except UnicodeError:
                _fail("input must be valid UTF-8 text")
            total_bytes += size
            if total_bytes > MAX_TOTAL_BYTES:
                _fail("snapshot exceeds 64 MiB input limit")
            if size > MAX_LINE_BYTES:
                _fail("input line exceeds 1 MiB limit")
            if not line.strip():
                continue
            try:
                record = json.loads(line, object_pairs_hook=_unique_keys,
                                    parse_constant=lambda _: _fail("invalid JSON constant"))
            except _ValidationError:
                raise
            except (ValueError, RecursionError):
                _fail("malformed JSON record")
            if snapshot is None:
                snapshot = _header(record)
                coverage = {r["repository"]: r["pull_requests"] for r in snapshot["repositories"]}
                continue
            record_count += 1
            if record_count > MAX_RECORDS:
                _fail("snapshot exceeds 100000 pull request record limit")
            row = _pull_request(record, coverage)
            key = row["repository"], row["number"]
            if key in rows and rows[key] != row:
                _fail("contradictory duplicate pull request")
            rows[key] = row
        except ValueError as exc:
            # All messages raised above are fixed strings, not JSON decoder
            # messages (which could contain payload fragments).
            raise ValueError(f"line {line_number}: {exc}") from None
    if snapshot is None:
        raise ValueError("line 1: missing snapshot header")
    snapshot["pull_requests"] = [rows[key] for key in sorted(rows)]
    return snapshot
