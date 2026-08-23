#!/usr/bin/env python3
"""Update TBA conference deadlines from explicitly configured official CFP pages.

The extractor is deliberately configuration-driven: a page must match a label-specific
regular expression and the resulting year must be plausible for the conference.  This
keeps a generic date elsewhere on a conference site from silently becoming a deadline.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "_data" / "conferences.yml"
SOURCES_FILE = ROOT / "_data" / "deadline_sources.yml"
USER_AGENT = "Paper-deadlines deadline monitor (+https://github.com/buptslb/Paper-deadlines)"


def visible_text(raw_html: str) -> str:
    raw_html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw_html)
    text = re.sub(r"(?s)<[^>]+>", " ", raw_html)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return visible_text(response.read().decode("utf-8", errors="replace"))


def extract(text: str, rule: dict, conference_year: int) -> str | None:
    match = re.search(rule["pattern"], text, flags=re.IGNORECASE)
    if not match:
        return None
    value = match.group("date").strip()
    parsed = None
    for fmt in rule["formats"]:
        try:
            parsed = datetime.strptime(value, fmt)
            break
        except ValueError:
            pass
    if parsed is None:
        raise ValueError(f"matched an unsupported date: {value!r}")
    # Submission normally occurs in the conference year or the preceding year.
    if parsed.year not in {conference_year - 1, conference_year}:
        raise ValueError(f"date year {parsed.year} is not plausible for {conference_year}")
    time = rule.get("time", "23:59:59")
    datetime.strptime(time, "%H:%M:%S")
    return f"{parsed:%Y-%m-%d} {time}"


def replace_field(document: str, conference_id: str, field: str, value: str) -> str:
    blocks = re.split(r"(?=^- title: )", document, flags=re.MULTILINE)
    found = False
    for index, block in enumerate(blocks):
        if not re.search(rf"^  id:\s*{re.escape(conference_id)}\s*$", block, re.MULTILINE):
            continue
        pattern = rf"(^  {re.escape(field)}:\s*).*$"
        if re.search(pattern, block, re.MULTILINE):
            blocks[index] = re.sub(pattern, rf"\g<1>'{value}'", block, count=1, flags=re.MULTILINE)
        else:
            # Optional fields (notably abstract_deadline) are inserted next to deadline.
            blocks[index] = re.sub(
                r"(^  deadline:.*$)", rf"  {field}: '{value}'\n\1", block,
                count=1, flags=re.MULTILINE,
            )
        found = True
        break
    if not found:
        raise ValueError(f"conference id {conference_id!r} not found")
    return "".join(blocks)


def remove_field(document: str, conference_id: str, field: str) -> str:
    blocks = re.split(r"(?=^- title: )", document, flags=re.MULTILINE)
    for index, block in enumerate(blocks):
        if re.search(rf"^  id:\s*{re.escape(conference_id)}\s*$", block, re.MULTILINE):
            blocks[index] = re.sub(rf"^  {re.escape(field)}:.*\n", "", block, flags=re.MULTILINE)
            break
    return "".join(blocks)


def run(apply: bool, only: set[str] | None = None) -> tuple[list[str], list[str]]:
    conferences = {item["id"]: item for item in yaml.safe_load(DATA_FILE.read_text())}
    sources = yaml.safe_load(SOURCES_FILE.read_text())["sources"]
    document = DATA_FILE.read_text()
    changes, warnings = [], []
    for source in sources:
        conference_id = source["id"]
        if only and conference_id not in only:
            continue
        conference = conferences.get(conference_id)
        if not conference:
            warnings.append(f"{conference_id}: not present in conferences.yml")
            continue
        if str(conference.get("deadline", "")).lower() not in {"tba", "tbd"}:
            continue
        try:
            page = fetch(source["url"])
            updates = {}
            for field in ("abstract_deadline", "deadline"):
                if field in source:
                    candidate = extract(page, source[field], int(conference["year"]))
                    if candidate:
                        updates[field] = candidate
            if "deadline" not in updates:
                warnings.append(f"{conference_id}: official page still has no parseable paper deadline")
                continue
            for field, value in updates.items():
                document = replace_field(document, conference_id, field, value)
                changes.append(f"{conference_id}: {field} -> {value}")
            for field, value in source.get("set", {}).items():
                document = replace_field(document, conference_id, field, str(value))
            for field in (
                "previous_deadline", "previous_edition", "previous_deadline_date",
                "previous_deadline_timezone", "previous_edition_year",
            ):
                document = remove_field(document, conference_id, field)
        except Exception as exc:  # one broken site must not prevent checking the rest
            warnings.append(f"{conference_id}: {exc}")
    if apply and changes:
        DATA_FILE.write_text(document)
    return changes, warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write verified changes")
    parser.add_argument("--only", action="append", help="check only this conference id")
    args = parser.parse_args()
    changes, warnings = run(args.apply, set(args.only) if args.only else None)
    for item in changes:
        print(f"UPDATE {item}")
    for item in warnings:
        print(f"NOTICE {item}", file=sys.stderr)
    print(f"Checked sources: {len(changes)} field update(s) found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
