from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class LinkAuditResult:
    markdown_path: Path
    json_path: Path
    finding_count: int
    warning_count: int
    review_count: int


def _load(snapshot: Path, name: str, default: Any) -> Any:
    try:
        return json.loads((snapshot / name).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _records(snapshot: Path, stem: str) -> list[dict[str, Any]]:
    value = _load(snapshot, f"{stem}.json", [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _md(value: Any) -> str:
    return str(value if value is not None else "").replace("\n", " ").replace("\r", " ").replace("|", "\\|")


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value for key, value in attrs}
        lowered = tag.casefold()
        if lowered == "a" and values.get("href"):
            self.references.append(("link", str(values["href"])))
        elif lowered in {"img", "source", "video", "audio", "iframe"} and values.get("src"):
            self.references.append(("embedded resource", str(values["src"])))


def _extract_html(source_type: str, source_name: str, html: Any) -> list[dict[str, str]]:
    if not html:
        return []
    parser = _LinkParser()
    try:
        parser.feed(str(html))
    except Exception:
        return []
    return [
        {"source_type": source_type, "source": source_name, "reference_type": kind, "url": url}
        for kind, url in parser.references
    ]


def _finding(severity: str, area: str, message: str, item: str = "") -> dict[str, str]:
    return {"severity": severity, "area": area, "item": item, "message": message}


def _target_inventory(snapshot: Path) -> dict[str, set[str]]:
    assignments = _records(snapshot, "assignments")
    modules = _records(snapshot, "modules")
    files = _records(snapshot, "files")
    pages = _records(snapshot, "pages")
    discussions = _records(snapshot, "discussions")
    classic = _records(snapshot, "classic-quizzes")
    new = _records(snapshot, "new-quizzes")

    quiz_ids = {str(item.get("id")) for item in classic if item.get("id") is not None}
    quiz_ids.update(str(item.get("id")) for item in new if item.get("id") is not None)
    quiz_ids.update(str(item.get("assignment_id")) for item in new if item.get("assignment_id") is not None)

    return {
        "assignments": {str(item.get("id")) for item in assignments if item.get("id") is not None},
        "modules": {str(item.get("id")) for item in modules if item.get("id") is not None},
        "files": {str(item.get("id")) for item in files if item.get("id") is not None},
        "pages": {str(item.get("url")) for item in pages if item.get("url")},
        "discussions": {str(item.get("id")) for item in discussions if item.get("id") is not None},
        "quizzes": quiz_ids,
    }


def _classify_canvas_path(path: str, course_id: str, inventory: dict[str, set[str]]) -> tuple[str, str, str | None]:
    match = re.search(r"/courses/(\d+)(?:/|$)", path)
    if not match:
        return "canvas", "Canvas link", None
    linked_course = match.group(1)
    if linked_course != course_id:
        return "cross_course", f"Canvas course {linked_course}", None

    checks = [
        (r"/assignments/(\d+)(?:/|$)", "assignments", "Assignment"),
        (r"/modules/(\d+)(?:/|$)", "modules", "Module"),
        (r"/files/(\d+)(?:/|$)", "files", "File"),
        (r"/quizzes/(\d+)(?:/|$)", "quizzes", "Quiz"),
        (r"/discussion_topics/(\d+)(?:/|$)", "discussions", "Discussion"),
        (r"/(?:pages|wiki)/([^/?#]+)(?:/|$)", "pages", "Page"),
    ]
    for pattern, key, label in checks:
        target = re.search(pattern, path)
        if not target:
            continue
        target_id = target.group(1)
        if target_id in inventory[key]:
            return "valid_internal", f"{label} {target_id}", target_id
        return "missing_internal", f"Missing {label.lower()} {target_id}", target_id
    return "current_course", "Current course", course_id


def audit_links(snapshot: Path) -> LinkAuditResult:
    snapshot = snapshot.resolve()
    manifest = _load(snapshot, "manifest.json", {})
    course = _load(snapshot, "course.json", {})
    course_id = str(manifest.get("course_id") or "")
    base_url = str(manifest.get("base_url") or "")
    canvas_host = urlparse(base_url).netloc.casefold()
    inventory = _target_inventory(snapshot)

    refs: list[dict[str, str]] = []
    refs.extend(_extract_html("Syllabus", "Course syllabus", course.get("syllabus_body")))
    for item in _records(snapshot, "pages"):
        refs.extend(_extract_html("Page", str(item.get("title") or item.get("url") or "unnamed page"), item.get("body")))
    for item in _records(snapshot, "assignments"):
        refs.extend(_extract_html("Assignment", str(item.get("name") or item.get("id") or "unnamed assignment"), item.get("description")))
    for item in _records(snapshot, "classic-quizzes"):
        refs.extend(_extract_html("Classic Quiz", str(item.get("title") or item.get("id") or "unnamed quiz"), item.get("description")))
    for item in _records(snapshot, "new-quizzes"):
        refs.extend(_extract_html("New Quiz", str(item.get("title") or item.get("id") or "unnamed quiz"), item.get("instructions")))
    for item in _records(snapshot, "discussions"):
        refs.extend(_extract_html("Discussion", str(item.get("title") or item.get("id") or "unnamed discussion"), item.get("message")))
    for item in _records(snapshot, "announcements"):
        refs.extend(_extract_html("Announcement", str(item.get("title") or item.get("id") or "unnamed announcement"), item.get("message")))

    for group in _records(snapshot, "module-items"):
        for item in group.get("items") or []:
            if not isinstance(item, dict):
                continue
            external = item.get("external_url")
            if external:
                refs.append({
                    "source_type": "Module item",
                    "source": str(item.get("title") or item.get("id") or "unnamed item"),
                    "reference_type": "external URL",
                    "url": str(external),
                })

    findings: list[dict[str, str]] = []
    domains: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []

    for ref in refs:
        raw = str(ref["url"]).strip()
        parsed = urlparse(raw)
        scheme = parsed.scheme.casefold()
        host = parsed.netloc.casefold()
        classification = "other"
        detail = "Other reference"
        target = None

        if raw.startswith("#"):
            classification = "fragment"
            detail = "Page fragment"
        elif scheme in {"mailto", "tel"}:
            classification = scheme
            detail = scheme
        elif raw.startswith("/"):
            classification, detail, target = _classify_canvas_path(parsed.path or raw, course_id, inventory)
        elif scheme in {"http", "https"}:
            if host:
                domains[host] += 1
            if host == canvas_host:
                classification, detail, target = _classify_canvas_path(parsed.path, course_id, inventory)
            else:
                classification = "external"
                detail = host or "External URL"
                if scheme == "http":
                    findings.append(_finding("review", "external link", "Uses plain HTTP rather than HTTPS.", f"{ref['source_type']}: {ref['source']}"))
        elif scheme == "javascript":
            classification = "javascript"
            detail = "javascript: URL"
            findings.append(_finding("review", "content link", "Contains a javascript: URL.", f"{ref['source_type']}: {ref['source']}"))
        elif not scheme:
            classification = "relative"
            detail = "Relative URL"

        if classification == "missing_internal":
            findings.append(_finding("warning", "internal Canvas link", f"Points to {detail.lower()}, which is not in the captured course inventory: {raw}", f"{ref['source_type']}: {ref['source']}"))
        elif classification == "cross_course":
            findings.append(_finding("review", "cross-course Canvas link", f"Points to {detail} rather than the current course: {raw}", f"{ref['source_type']}: {ref['source']}"))

        rows.append({**ref, "classification": classification, "detail": detail, "target": target, "domain": host})

    summary = {
        "references": len(rows),
        "valid_internal_targets": sum(1 for item in rows if item["classification"] == "valid_internal"),
        "missing_internal_targets": sum(1 for item in rows if item["classification"] == "missing_internal"),
        "cross_course_links": sum(1 for item in rows if item["classification"] == "cross_course"),
        "external_links_and_resources": sum(1 for item in rows if item["classification"] == "external"),
        "external_domains": len(domains),
    }

    payload = {
        "schema_version": 1,
        "course_id": course_id,
        "course_name": manifest.get("course_name"),
        "read_only": True,
        "summary": summary,
        "findings": findings,
        "external_domains": dict(sorted(domains.items())),
        "references": rows,
        "scope_note": "Internal Canvas targets are checked against the captured snapshot. External URLs are inventoried by domain but are not fetched or network-validated.",
    }
    json_path = snapshot / "link-audit.json"
    markdown_path = snapshot / "link-audit.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Link and internal-reference audit",
        "",
        f"- Course: **{manifest.get('course_name', 'unnamed course')}**",
        f"- Course code: `{manifest.get('course_code', '')}`",
        f"- Canvas course ID: `{course_id}`",
        "- Mode: **read-only**. No Canvas content is changed.",
        "",
        "Checks links and embedded-resource references found in captured course HTML. Internal Canvas targets are matched against the snapshot. External URLs are inventoried by domain but are not fetched or network-validated.",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key.replace('_', ' ').title()}: **{value}**")

    lines.extend(["", "## Attention / review", ""])
    actionable = [item for item in findings if item["severity"] in {"warning", "review"}]
    if actionable:
        for item in actionable:
            label = f" **{_md(item['item'])}**:" if item.get("item") else ""
            lines.append(f"- **{item['severity'].upper()} · {_md(item['area'])}**{label} {_md(item['message'])}")
    else:
        lines.append("None found.")

    lines.extend(["", "## External domains", ""])
    if domains:
        lines.extend(["| Domain | References |", "|---|---:|"])
        for domain, count in sorted(domains.items()):
            lines.append(f"| {_md(domain)} | {count} |")
    else:
        lines.append("None found.")

    lines.extend([
        "",
        "## Reference inventory",
        "",
        "| Source type | Source | Kind | Classification | Target / domain | URL |",
        "|---|---|---|---|---|---|",
    ])
    for item in rows:
        lines.append(
            f"| {_md(item['source_type'])} | {_md(item['source'])} | {_md(item['reference_type'])} | "
            f"{_md(item['classification'])} | {_md(item['detail'])} | {_md(item['url'])} |"
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    counts = Counter(item["severity"] for item in findings)
    return LinkAuditResult(
        markdown_path=markdown_path,
        json_path=json_path,
        finding_count=len(findings),
        warning_count=counts.get("warning", 0),
        review_count=counts.get("review", 0),
    )
