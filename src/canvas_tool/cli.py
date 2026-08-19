from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .api import CanvasApiError, CanvasClient
from .compare import compare_snapshots
from .config import ConfigError, load_config
from .course import CourseTargetError, resolve_course
from .course_audit import audit_course
from .date_audit import audit_dates
from .duplicates import audit_snapshot
from .recon import Recon
from .semester import build_semester_weeks, format_day, parse_date, render_week_text


def project_root() -> Path:
    configured = os.environ.get("CANVAS_TOOL_ROOT")
    if configured:
        return Path(configured).resolve()
    return Path.cwd().resolve()


def client_from_config() -> tuple[Any, CanvasClient]:
    config = load_config()
    return config, CanvasClient(config.base_url, config.api_token)


def command_doctor(args: argparse.Namespace) -> int:
    config, client = client_from_config()
    target = resolve_course(args.course, config.base_url)
    course = client.request_json("GET", f"/api/v1/courses/{target.course_id}?include[]=permissions&include[]=term")
    print(f"PASS configuration: {config.source or 'environment'}")
    print(f"PASS Canvas origin: {target.base_url}")
    print(f"PASS course ID: {target.course_id}")
    print("PASS API authentication and course access")
    print(f"Course: {course.get('name','unnamed')} ({course.get('course_code','no course code')})")
    return 0


def command_courses(args: argparse.Namespace) -> int:
    _config, client = client_from_config()
    courses = client.paginate("/api/v1/users/self/courses?include[]=term&state[]=unpublished&state[]=available&state[]=completed")
    needle = (args.search or "").casefold()
    if needle:
        courses = [item for item in courses if any(needle in str(value or "").casefold() for value in (item.get("name"), item.get("course_code"), item.get("sis_course_id"), (item.get("term") or {}).get("name")))]
    courses.sort(key=lambda item: ((item.get("term") or {}).get("end_at") or item.get("end_at") or item.get("start_at") or ""), reverse=True)
    print("ID\tCOURSE CODE\tTERM\tSTATE\tNAME")
    for item in courses:
        print("\t".join([str(item.get("id", "")), str(item.get("course_code") or ""), str((item.get("term") or {}).get("name") or ""), str(item.get("workflow_state") or ""), str(item.get("name") or "")]))
    return 0


def command_inspect(args: argparse.Namespace) -> int:
    config, client = client_from_config()
    target = resolve_course(args.course, config.base_url)
    course = client.request_json("GET", f"/api/v1/courses/{target.course_id}?include[]=permissions&include[]=term")
    keys = ["id", "name", "course_code", "sis_course_id", "workflow_state", "start_at", "end_at", "time_zone", "default_view", "apply_assignment_group_weights", "term", "permissions"]
    print(json.dumps({key: course.get(key) for key in keys}, indent=2, ensure_ascii=False))
    return 0


def command_recon(args: argparse.Namespace) -> int:
    _config, client = client_from_config()
    output = Path(args.output).expanduser().resolve() if args.output else None
    result = Recon(client, project_root()).run(args.course, output)
    print(result.path)
    return 0


def command_diff(args: argparse.Namespace) -> int:
    _config, client = client_from_config()
    recon = Recon(client, project_root())
    a = recon.run(args.course_a).path
    b = recon.run(args.course_b).path
    summary, detail, changed = compare_snapshots(a, b, project_root())
    ma = json.loads((a / "manifest.json").read_text(encoding="utf-8"))
    mb = json.loads((b / "manifest.json").read_text(encoding="utf-8"))
    print("Course comparison")
    print(f"  A: {ma['course_name']} ({ma.get('course_code','')}, {ma['course_id']})")
    print(f"  B: {mb['course_name']} ({mb.get('course_code','')}, {mb['course_id']})")
    if not changed:
        print("  Result: no structural/content differences after normalization")
    else:
        print("  Changed areas:")
        for area, left, right in changed:
            print(f"    - {area}" if left == "-" else f"    - {area:<24} {left} -> {right}")
    print(f"  Summary: {summary}")
    print(f"  Detailed diff: {detail}")
    return 0


def command_duplicates(args: argparse.Namespace) -> int:
    _config, client = client_from_config()
    snapshot = Recon(client, project_root()).run(args.course).path
    result = audit_snapshot(snapshot)
    print("Duplicate content audit")
    print(f"  High-confidence candidates: {result.high_confidence}")
    print(f"  Same-name review items:     {result.review}")
    print(f"  Similar-name candidates:    {result.similar_names}")
    print("  Canvas changes:             none (read-only)")
    print(f"  Report: {result.markdown_path}")
    print(f"  JSON:   {result.json_path}")
    return 0


def command_audit(args: argparse.Namespace) -> int:
    _config, client = client_from_config()
    root = project_root()
    snapshot = Recon(client, root).run(args.course).path
    calendar = Path(args.calendar).expanduser().resolve() if args.calendar else None
    result = audit_course(snapshot, root, calendar)
    print("Course audit")
    print(f"  Weekly structure issues:    {result.structure_issue_count}")
    print(f"  Date/schedule issues:       {result.date_issue_count}")
    print(f"  Duplicate candidates:       {result.duplicate_count}")
    print("  Canvas changes:             none (read-only)")
    print(f"  Report: {result.markdown_path}")
    print(f"  JSON:   {result.json_path}")
    return 0


def command_dates_weeks(args: argparse.Namespace) -> int:
    first = parse_date(args.first_class, "first class date")
    last = parse_date(args.last_class, "last class date")
    breaks = [
        {"name": name, "start": start, "end": end}
        for name, start, end in (args.break_periods or [])
    ]
    weeks = build_semester_weeks(first, last, break_weeks=breaks)
    instructional_weeks = max((week.week_number or 0 for week in weeks), default=0)
    print(f"First day of class: {format_day(first)}")
    print(f"Last day of class:  {format_day(last)}")
    print()
    print(render_week_text(weeks))
    print(f"\nNumbered instructional weeks: {instructional_weeks}")
    return 0


def command_dates_audit(args: argparse.Namespace) -> int:
    _config, client = client_from_config()
    root = project_root()
    snapshot = Recon(client, root).run(args.course).path
    calendar = Path(args.calendar).expanduser().resolve() if args.calendar else None
    result = audit_dates(snapshot, root, calendar)
    print("Date audit")
    print(f"  Calendar:          {result.calendar_name or 'none matched'}")
    print(f"  Assignments:       {result.assignment_count}")
    print(f"  Dated:             {result.dated_count}")
    print(f"  Missing due date:  {result.undated_count}")
    print(f"  Review flags:      {result.issue_count}")
    print("  Canvas changes:    none (read-only)")
    print(f"  Report: {result.markdown_path}")
    print(f"  JSON:   {result.json_path}")
    return 0


def command_api(args: argparse.Namespace) -> int:
    _config, client = client_from_config()
    value = client.paginate(args.target) if args.method.upper() == "GET" and args.paginate else client.request_json(args.method.upper(), args.target)
    print(json.dumps(value, indent=2, ensure_ascii=False))
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="canvas-tool", description="Canvas LMS course inspection and semester rollover tooling")
    p.add_argument("--version", action="version", version=f"canvas-tool {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    courses = sub.add_parser("courses", help="list/search your Canvas courses"); courses.add_argument("search", nargs="?"); courses.set_defaults(func=command_courses)
    doctor = sub.add_parser("doctor", help="verify configuration, authentication, and course access"); doctor.add_argument("course"); doctor.set_defaults(func=command_doctor)
    inspect = sub.add_parser("inspect", help="inspect course identity and permissions"); inspect.add_argument("course"); inspect.set_defaults(func=command_inspect)
    for name in ("recon", "snapshot"):
        recon = sub.add_parser(name, help="capture a sanitized course snapshot"); recon.add_argument("course"); recon.add_argument("output", nargs="?"); recon.set_defaults(func=command_recon)
    diff = sub.add_parser("diff", help="recon and compare two courses"); diff.add_argument("course_a"); diff.add_argument("course_b"); diff.set_defaults(func=command_diff)
    duplicates = sub.add_parser("duplicates", help="recon a course and report duplicate-content candidates (read-only)"); duplicates.add_argument("course"); duplicates.set_defaults(func=command_duplicates)
    audit = sub.add_parser("audit", help="recon a course and run structural, date, and duplicate checks (read-only)")
    audit.add_argument("course")
    audit.add_argument("--calendar", help="optional institutional calendar JSON; otherwise auto-match calendars/ by Canvas host and term")
    audit.set_defaults(func=command_audit)

    dates = sub.add_parser("dates", help="semester calendar and Canvas date tools")
    dates_sub = dates.add_subparsers(dest="dates_command", required=True)
    weeks = dates_sub.add_parser(
        "weeks",
        help="number Sunday-Saturday instructional weeks from first to last class day",
        description="Build a Sunday-Saturday semester week reference. All dates must use YYYY-MM-DD, for example 2026-08-24.",
        epilog='Example:\n  canvas-tool dates weeks 2026-08-24 2026-12-18 --break "Thanksgiving Break" 2026-11-23 2026-11-27',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    weeks.add_argument("first_class", metavar="FIRST_CLASS_YYYY-MM-DD", help="first day of class in YYYY-MM-DD format")
    weeks.add_argument("last_class", metavar="LAST_CLASS_YYYY-MM-DD", help="last day of class in YYYY-MM-DD format")
    weeks.add_argument(
        "--break",
        dest="break_periods",
        action="append",
        nargs=3,
        metavar=("NAME", "START_YYYY-MM-DD", "END_YYYY-MM-DD"),
        help="unnumbered break week; break start/end dates use YYYY-MM-DD; repeat as needed",
    )
    weeks.set_defaults(func=command_dates_weeks)
    dates_audit = dates_sub.add_parser("audit", help="recon a course and audit assignment dates (read-only)")
    dates_audit.add_argument("course")
    dates_audit.add_argument("--calendar", help="optional institutional calendar JSON; otherwise auto-match calendars/ by Canvas host and term")
    dates_audit.set_defaults(func=command_dates_audit)

    api = sub.add_parser("api", help="low-level Canvas API escape hatch"); api.add_argument("method"); api.add_argument("target"); api.add_argument("--paginate", action="store_true", help="follow Canvas pagination for GET collections"); api.set_defaults(func=command_api)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (ConfigError, CourseTargetError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except CanvasApiError as exc:
        print(str(exc), file=sys.stderr)
        body = exc.pretty_body()
        if body:
            print(body, file=sys.stderr)
        return 22
