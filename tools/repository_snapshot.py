#!/usr/bin/env python3
"""Opt-in, read-only GitHub collector for the fork-local ``sigwood repos`` command.

This is deliberately outside the analyzer. It uses an already authenticated
GitHub CLI; it accepts no credentials and reads no repository files, hooks, or agent instructions.
Only explicit OWNER/REPO arguments are queried. Raw responses never reach output.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections.abc import Callable
from typing import Any


_REPOSITORY = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}\Z")
_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
_MAX_PAGES = 100
_PAGE_SIZE = 100


class CollectionError(ValueError):
    """A fixed, non-sensitive explanation safe for the command boundary."""


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse's normal error text can echo arbitrary arguments. Keep
        # invalid usage distinct from exit 2's valid-but-incomplete artifact.
        raise CollectionError("invalid arguments; run --help for usage")


def gh_get(endpoint: str) -> Any:
    """One explicit GET via gh; errors cannot echo credentials or API bodies."""
    env = os.environ.copy()
    env.pop("GH_DEBUG", None)
    try:
        result = subprocess.run(
            ["gh", "api", "--hostname", "github.com", "--method", "GET",
             "--header", "Accept: application/vnd.github+json",
             "--header", "X-GitHub-Api-Version: 2022-11-28", endpoint],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
            check=False, env=env,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        raise CollectionError("GitHub CLI request unavailable") from None
    if result.returncode:
        raise CollectionError("GitHub CLI request unavailable")
    if len(result.stdout) > 32 * 1024 * 1024:
        raise CollectionError("GitHub CLI response exceeds the collection limit")
    try:
        return json.loads(result.stdout)
    except (ValueError, RecursionError):
        raise CollectionError("GitHub CLI returned an invalid response") from None


def _pages(
    get: Callable[[str], Any], endpoint: str, field: str | None = None,
) -> tuple[list[Any], str]:
    """Paginate to exhaustion, retaining explicitly partial evidence on failure.

    The cap is a resource bound, never a claim of completeness. Check-run totals
    are cross-checked, including changes during non-atomic collection.
    """
    items: list[Any] = []
    totals: set[int] = set()
    previous_batches: set[str] = set()
    for page in range(1, _MAX_PAGES + 1):
        separator = "&" if "?" in endpoint else "?"
        try:
            payload = get(f"{endpoint}{separator}per_page={_PAGE_SIZE}&page={page}")
        except CollectionError:
            return items, "partial" if page > 1 else "unavailable"
        batch = payload.get(field) if field and isinstance(payload, dict) else payload
        if not isinstance(batch, list):
            return items, "partial" if page > 1 else "unavailable"
        fingerprint = json.dumps(batch, sort_keys=True)
        if batch and fingerprint in previous_batches:
            return items, "partial"
        previous_batches.add(fingerprint)
        if field:
            total = payload.get("total_count") if isinstance(payload, dict) else None
            if type(total) is not int or total < 0:
                return items, "partial" if page > 1 else "unavailable"
            totals.add(total)
        items.extend(batch)
        if len(batch) < _PAGE_SIZE:
            complete = not totals or (len(totals) == 1 and next(iter(totals)) == len(items))
            return items, "complete" if complete else "partial"
    return items, "partial"


def _text(value: Any) -> bool:
    return (isinstance(value, str) and bool(value.strip()) and len(value) <= 256
            and not any(unicodedata.category(c).startswith("C") for c in value)
            and not any(c in "\u2028\u2029" for c in value))


def _sha(value: Any) -> str | None:
    return value.lower() if isinstance(value, str) and _SHA.fullmatch(value) else None


def _boolean(value: Any) -> bool | None:
    return value if type(value) is bool else None


def _runs(get: Callable[[str], Any], repository: str, head: str) -> dict:
    raw, coverage = _pages(get, f"repos/{repository}/commits/{head}/check-runs?filter=latest", "check_runs")
    items = []
    seen: dict[int, dict] = {}
    suites: set[int] = set()
    for item in raw:
        if not isinstance(item, dict):
            coverage = "partial"
            continue
        identity = item.get("id")
        if (type(identity) is not int or identity <= 0
                or _sha(item.get("head_sha")) != head
                or not _text(item.get("name")) or not _text(item.get("status"))
                or (item.get("conclusion") is not None and not _text(item["conclusion"]))):
            coverage = "partial"
            continue
        normalized = {key: item.get(key) for key in ("name", "status", "conclusion")}
        if identity in seen:
            # Pagination moving under us is not a complete snapshot, even if
            # the repeated row is identical. Keep disagreement conservatively.
            coverage = "partial"
            if normalized == seen[identity]:
                continue
        seen[identity] = normalized
        items.append(normalized)
        suite = item.get("check_suite")
        if isinstance(suite, dict) and type(suite.get("id")) is int:
            suites.add(suite["id"])
    # GitHub limits this endpoint to the 1000 most recent check suites.
    # At the boundary do not represent its visible subset as exhaustive.
    if len(suites) >= 1000:
        coverage = "partial"
    return {"coverage": coverage, "items": items}


def _statuses(get: Callable[[str], Any], repository: str, head: str) -> dict:
    raw, coverage = _pages(get, f"repos/{repository}/commits/{head}/statuses")
    items = []
    seen: set[str] = set()
    # GitHub returns newest first; contexts are case-insensitive. Older failures
    # must not overwrite a newer result for the same context.
    for item in raw:
        if not isinstance(item, dict) or not _text(item.get("context")):
            coverage = "partial"
            continue
        key = item["context"].casefold()
        if key in seen:
            continue
        seen.add(key)
        if not _text(item.get("state")):
            coverage = "partial"
            continue
        items.append({"name": item["context"], "state": item["state"]})
    return {"coverage": coverage, "items": items}


def collect(
    repositories: list[str], get: Callable[[str], Any] = gh_get,
    observed_at: str | None = None,
) -> list[dict]:
    """Return sanitized v1 records. Transport is injectable for offline tests."""
    selected = set()
    for repository in repositories:
        if (not isinstance(repository, str) or not _REPOSITORY.fullmatch(repository)
                or not repository.split("/")[1].strip(".")):
            raise CollectionError("repositories must be explicit OWNER/REPO names")
        selected.add(repository.lower())
    if not selected:
        raise CollectionError("at least one explicit OWNER/REPO is required")
    coverage_rows = []
    records = []
    for repository in sorted(selected):
        raw, coverage = _pages(
            get, f"repos/{repository}/pulls?state=open&sort=created&direction=asc",
        )
        seen: set[int] = set()
        for listed in raw:
            number = listed.get("number") if isinstance(listed, dict) else None
            if type(number) is not int or number <= 0 or number in seen:
                coverage = "partial"
                continue
            seen.add(number)
            try:
                detail = get(f"repos/{repository}/pulls/{number}")
            except CollectionError:
                detail = None
            if (not isinstance(detail, dict) or type(detail.get("number")) is not int
                    or detail.get("number") != number
                    or detail.get("state") not in ("open", "closed")):
                # List data still carries a captured head, but cannot establish
                # conflict status. Do not invent it from mergeable_state.
                detail = dict(listed)
                detail["mergeable"] = None
                coverage = "partial"
            elif detail["state"] == "closed":
                # PR closed during collection. Report the list as non-atomic,
                # not an open PR that can be acted on.
                coverage = "partial"
                continue
            head_data = detail.get("head")
            head = _sha(head_data.get("sha")) if isinstance(head_data, dict) else None
            if head is None:
                coverage = "partial"
                continue
            records.append({
                "type": "pull_request", "repository": repository,
                "number": number, "head_sha": head,
                "draft": _boolean(detail.get("draft")),
                "mergeable": _boolean(detail.get("mergeable")),
                "checks": {
                    "head_sha": head,
                    "check_runs": _runs(get, repository, head),
                    "statuses": _statuses(get, repository, head),
                },
            })
        coverage_rows.append({"repository": repository, "pull_requests": coverage})
    header = {
        "schema": "sigwood.repository-attention", "version": 1, "type": "snapshot",
        "observed_at": observed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "repositories": coverage_rows,
    }
    return [header, *sorted(records, key=lambda row: (row["repository"], row["number"]))]


def main(argv: list[str] | None = None) -> int:
    parser = _ArgumentParser(
        description="Read-only GitHub PR snapshot for sigwood repos; stdout may contain private metadata.",
        epilog="Uses installed, authenticated gh. No clone, daemon, repository writes or automated fixes.",
    )
    parser.add_argument("repositories", metavar="OWNER/REPO", nargs="+")
    try:
        args = parser.parse_args(argv)
        records = collect(args.repositories)
        # Validate before writing any stdout; oversized/unsupported output must
        # not become a truncated artifact which looks complete at a glance.
        from sigwood.repos import parse_snapshot
        lines = [json.dumps(record, sort_keys=True, ensure_ascii=True) + "\n" for record in records]
        try:
            parse_snapshot(lines)
        except ValueError:
            raise CollectionError("snapshot exceeds format limits or contains unsupported metadata; no output written") from None
        for line in lines:
            print(line, end="")
    except CollectionError as exc:
        print(f"repository_snapshot: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 141
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
        return 130
    # Partial data is still a valid useful artifact, but callers must not
    # mistake a failed credential/rate-limit request for an empty healthy fleet.
    incomplete = any(row["pull_requests"] != "complete" for row in records[0]["repositories"])
    incomplete |= any(
        row["checks"][source]["coverage"] != "complete"
        for row in records[1:] for source in ("check_runs", "statuses")
    )
    if incomplete:
        print("repository_snapshot: incomplete coverage; inspect the digest before drawing conclusions", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
