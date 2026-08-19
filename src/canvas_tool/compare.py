from __future__ import annotations

import difflib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .report_index import refresh_report_index


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def compare_snapshots(a: Path, b: Path, root: Path) -> tuple[Path, Path, list[tuple[str, str, str]]]:
    ma = _load(a / "manifest.json")
    mb = _load(b / "manifest.json")
    na = _load(a / "normalized.json")
    nb = _load(b / "normalized.json")
    ia, ib = str(ma["course_id"]), str(mb["course_id"])
    directory = root / "comparisons" / f"{ia}-vs-{ib}"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    diff_path = directory / f"{stamp}.diff"
    summary_path = directory / f"{stamp}-summary.md"

    a_text = json.dumps(na, indent=2, ensure_ascii=False, sort_keys=False).splitlines(keepends=True)
    b_text = json.dumps(nb, indent=2, ensure_ascii=False, sort_keys=False).splitlines(keepends=True)
    diff_text = "".join(difflib.unified_diff(a_text, b_text, fromfile=f"course-{ia}/normalized.json", tofile=f"course-{ib}/normalized.json"))
    if not diff_text:
        diff_text = "No structural/content differences after normalization.\n"
    diff_path.write_text(diff_text, encoding="utf-8")

    changed: list[tuple[str, str, str]] = []
    for key in sorted(set(na) | set(nb)):
        if na.get(key) == nb.get(key):
            continue
        left, right = na.get(key), nb.get(key)
        if isinstance(left, list) and isinstance(right, list):
            changed.append((key, str(len(left)), str(len(right))))
        else:
            changed.append((key, "-", "-"))

    lines = [
        "# Canvas course comparison",
        "",
        f"- A: **{ma['course_name']}** (`{ma.get('course_code','')}`, ID `{ia}`)",
        f"- B: **{mb['course_name']}** (`{mb.get('course_code','')}`, ID `{ib}`)",
        "",
        "## Changed areas",
        "",
        "| Area | A count | B count |",
        "|---|---:|---:|",
    ]
    for area, left, right in changed:
        lines.append(f"| `{area}` | {left} | {right} |")
    lines += ["", f"[Detailed unified diff]({diff_path.name})"]
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    refresh_report_index(directory)
    return summary_path, diff_path, changed
