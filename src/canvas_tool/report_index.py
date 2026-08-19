from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_INDEX_LINK = "[← Report index](README.md)"
_PRIORITY = {
    "course-overview.md": 0,
    "comprehensive-audit.md": 1,
    "course-audit.md": 2,
    "date-audit.md": 3,
    "assignment-audit.md": 4,
    "module-audit.md": 5,
    "quiz-audit.md": 6,
    "question-bank-audit.md": 7,
    "grading-audit.md": 8,
    "content-audit.md": 9,
    "integration-audit.md": 10,
    "migration-audit.md": 11,
    "course-settings-audit.md": 12,
    "duplicate-audit.md": 13,
    "summary.md": 14,
}


def _load_manifest(directory: Path) -> dict[str, Any]:
    try:
        value = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _title(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip() or path.stem
    except OSError:
        pass
    return path.stem.replace("-", " ").title()


def _add_index_link(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if _INDEX_LINK in text:
        return

    lines = text.splitlines()
    if not lines:
        return

    if lines[0].startswith("# "):
        if len(lines) > 1 and lines[1] == "":
            lines[2:2] = [_INDEX_LINK, ""]
        else:
            lines[1:1] = ["", _INDEX_LINK, ""]
    else:
        lines[0:0] = [_INDEX_LINK, ""]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def refresh_report_index(directory: Path) -> Path:
    """Create a local Markdown contents page and backlink every generated report to it."""
    directory = directory.resolve()
    reports = [
        path
        for path in directory.glob("*.md")
        if path.is_file() and path.name != "README.md"
    ]
    reports.sort(key=lambda path: (_PRIORITY.get(path.name, 100), path.name.casefold()))

    for path in reports:
        _add_index_link(path)

    manifest = _load_manifest(directory)
    lines = ["# Report index", ""]
    if manifest:
        lines.extend([
            f"- Course: **{manifest.get('course_name', 'unnamed course')}**",
            f"- Course code: `{manifest.get('course_code', '')}`",
            f"- Canvas course ID: `{manifest.get('course_id', '')}`",
            "",
        ])

    lines.extend([
        "## Markdown reports",
        "",
        "| Report | File |",
        "|---|---|",
    ])
    if reports:
        for path in reports:
            lines.append(f"| [{_title(path)}]({path.name}) | `{path.name}` |")
    else:
        lines.append("| None yet | — |")

    index_path = directory / "README.md"
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return index_path
