from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit


class CourseTargetError(ValueError):
    pass


@dataclass(frozen=True)
class CourseTarget:
    base_url: str
    course_id: str


def origin(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc:
        raise CourseTargetError(f"invalid Canvas URL: {url}")
    return f"https://{parts.netloc}"


def assert_same_origin(candidate: str, configured: str) -> None:
    candidate_origin = origin(candidate)
    configured_origin = origin(configured)
    if candidate_origin != configured_origin:
        raise CourseTargetError(
            f"refusing to send Canvas credentials to {candidate_origin}; "
            f"configured origin is {configured_origin}"
        )


def resolve_course(target: str, configured_base_url: str) -> CourseTarget:
    configured = configured_base_url.rstrip("/")
    if re.fullmatch(r"\d+", target):
        return CourseTarget(configured, target)

    candidate = target
    if not candidate.startswith("https://") and re.match(r"^[^/]+/courses/\d+", candidate):
        candidate = "https://" + candidate

    match = re.match(r"^(https://[^/]+)/courses/(\d+)(?:[/\?#].*)?$", candidate)
    if not match:
        raise CourseTargetError(
            "expected a numeric Canvas course ID or URL containing /courses/<id>: " + target
        )

    base_url, course_id = match.groups()
    assert_same_origin(base_url, configured)
    return CourseTarget(base_url.rstrip("/"), course_id)
