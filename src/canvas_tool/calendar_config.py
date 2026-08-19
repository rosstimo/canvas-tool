from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _load_calendar_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Calendar must contain a JSON object: {path}")
    data["_path"] = str(path)
    return data


def find_calendar(
    root: Path,
    manifest: dict[str, Any],
    course: dict[str, Any],
    explicit: Path | None = None,
) -> dict[str, Any] | None:
    if explicit is not None:
        return _load_calendar_file(explicit.expanduser().resolve())

    host = (urlparse(str(manifest.get("base_url") or "")).hostname or "").casefold()
    term_name = str((course.get("term") or {}).get("name") or "").casefold()
    calendar_dir = root / "calendars"
    if not calendar_dir.is_dir():
        return None

    for path in sorted(calendar_dir.glob("*.json")):
        try:
            data = _load_calendar_file(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        calendar_host = str(data.get("canvas_host") or "").casefold()
        calendar_term = str(data.get("term_name") or "").casefold()
        if calendar_host == host and calendar_term == term_name:
            return data
    return None
