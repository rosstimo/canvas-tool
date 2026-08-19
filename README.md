# canvas-tool

A command-line tool for inspecting, comparing, auditing, and eventually managing Canvas LMS courses through the Canvas API.

## Python rewrite

Development has moved to Python 3.13 with `uv` for reproducible environments. The source checkout has a root launcher, so normal development use stays simple:

```bash
./canvas-tool doctor 18637
./canvas-tool courses RCET2265
./canvas-tool recon 18637
./canvas-tool overview 18637
./canvas-tool audit 18637
./canvas-tool diff 11657 18637
./canvas-tool duplicates 18637
./canvas-tool dates audit 18637
```

The launcher runs the Python CLI through the repository's locked `uv` project. Direct `uv` use also works:

```bash
uv run canvas-tool doctor 18637
```

The Python runtime currently has **no third-party runtime dependencies**. The standard library handles HTTP, JSON, configuration, dates, comparison, duplicate detection, and CLI parsing. `uv.lock` and `.python-version` keep development environments reproducible.

The older Bash implementation remains in `bin/` and `lib/` during the rewrite as a known-working reference implementation. New feature work should target the Python package under `src/canvas_tool/`.

## Configuration

For compatibility with the prototype, copy `.env.example` to `.env` and configure:

```text
CANVAS_BASE_URL=https://isu.instructure.com
CANVAS_API_TOKEN=...
```

`.env` is ignored by Git. Environment variables override file values. The Python configuration layer is also structured to support a per-user config file later, so packaged releases will not require running from a Git checkout.

## Current commands

```text
canvas-tool courses [search]
canvas-tool doctor <course-id-or-url>
canvas-tool inspect <course-id-or-url>
canvas-tool recon <course-id-or-url> [output-directory]
canvas-tool snapshot <course-id-or-url> [output-directory]
canvas-tool overview <course-id-or-url> [--calendar calendar.json]
canvas-tool audit <course-id-or-url> [--calendar calendar.json]
canvas-tool diff <course-a-id-or-url> <course-b-id-or-url>
canvas-tool duplicates <course-id-or-url>
canvas-tool dates weeks <FIRST_CLASS_YYYY-MM-DD> <LAST_CLASS_YYYY-MM-DD> [--break NAME START_YYYY-MM-DD END_YYYY-MM-DD]
canvas-tool dates audit <course-id-or-url> [--calendar calendar.json]
canvas-tool api <METHOD> <path-or-url> [--paginate]
```

Course targets accept all of these forms:

```text
17600
isu.instructure.com/courses/17600
https://isu.instructure.com/courses/17600
```

A URL must match `CANVAS_BASE_URL` before credentials are sent.

## Course overview

`canvas-tool overview COURSE` is the main "show me my course" workflow. It performs a fresh read-only recon, reads the semester calendar when available, safely retrieves module **Assign To** settings, and produces one report that exposes Canvas configuration that normally requires many separate clicks.

For every module the overview shows:

- module position, name, and published state
- **Assign To** target (`Everyone`, section/group targets, or a FERPA-safe count for specific-student overrides)
- optional module lock/unlock date using `Week | Day | Time | Date`
- prerequisite modules
- whether required items must be completed sequentially
- whether all or one required item must be completed
- every module item and its individual published state
- each item's Canvas type
- item completion requirement (`View`, `Submit`, `Mark done`, minimum score, etc.)
- for graded items: due date, assignment group/grade category, points possible, and attached rubric

The overview also compares the Assignments API with module contents and lists **graded items not represented in any module**. This catches gradebook objects that can be difficult to discover from the Modules page.

Names and titles are **display data only**. `canvas-tool` does not infer course structure, week numbers, dates, or correctness from arbitrary names such as `W07`, `Week 7`, or any other naming convention.

Results are written beside the snapshot as:

```text
course-overview.md
course-overview.json
module-overrides.json
```

Module override snapshots deliberately do not retain specific student IDs or names. A student-targeted module is summarized only as a count.

## Course audit

`canvas-tool audit COURSE` is the compact exception report. It uses structured Canvas/calendar fields only and currently highlights:

- graded objects without due dates
- due dates before the first class day or after the last class day
- due dates during configured breaks or holidays
- invalid unlock/due/lock ordering
- differentiated assignment dates that deserve review
- notable due-date clumps and strong due-time outliers
- module unlock dates outside the course or during no-class periods
- graded items returned by Canvas that are not represented in a module
- recon endpoints that could not be retrieved

It intentionally does **not** interpret names or titles. The full `course-overview.md` remains the primary at-a-glance view; the audit is only the shorter exception list.

Results are written beside the snapshot as:

```text
course-audit.md
course-audit.json
```

No Canvas content or dates are modified.

## Semester weeks and date audit

`canvas-tool dates weeks` builds a compact semester reference from the first and last class days. **All command-line dates use `YYYY-MM-DD`**, for example `2026-08-24`.

Weeks run **Sunday through Saturday**. The first and last class days are called out separately. A break supplied with `--break` remains visible in the sequence but has no instructional week number, and numbering resumes after the break.

Example:

```bash
./canvas-tool dates weeks 2026-08-24 2026-12-18 \
  --break "Thanksgiving Break" 2026-11-23 2026-11-27
```

`canvas-tool dates audit COURSE` performs a fresh read-only recon and checks structured Canvas dates against the matched semester calendar. The report uses:

- a compact `Week | Sunday-Saturday date range | Notes` semester reference
- `Week | Day | Date | Time` for graded-object due dates
- the same `Week | Day | Date | Time` convention for module unlock dates
- flags for missing dates, dates during breaks/holidays, bad availability ordering, differentiated-date assignments, due-date clumps, strong due-time outliers, and module unlock-date problems

Assignment/module names are never parsed to infer a week or expected date.

Results are written beside the snapshot as:

```text
date-audit.md
date-audit.json
```

No Canvas dates are modified.

## Recon

Recon intentionally avoids student rosters, enrollments, submissions, grades, quiz submissions, and discussion entries. The default output remains:

```text
snapshots/<canvas-host>/<course-id>/
```

Important files are:

- `summary.md` - human-readable inventory
- `manifest.json` - snapshot identity and capture metadata
- `normalized.json` - structural/content representation for cross-semester comparison
- `errors.json` - endpoints that were unavailable or denied
- the remaining JSON files - sanitized API responses for Canvas resource types

Generated snapshots and comparisons are ignored by Git.

## Duplicate audit

`canvas-tool duplicates COURSE` remains a separate specialized review tool. It audits normalized course content for duplicate candidates and does not modify Canvas.

The duplicate heuristic uses names/content similarity and therefore is intentionally **not** part of the convention-free course audit. Its findings are review candidates only, especially the lower-confidence similar-name category.

Results are written beside the snapshot as:

```text
duplicate-audit.md
duplicate-audit.json
```

Matching names are intentionally never treated as permission to delete content. Any future cleanup feature will build an explicit review/dry-run plan before writes are allowed.

## Tests

Python tests use the standard library and require no real Canvas token:

```bash
uv run python -m unittest discover -s tests_py -v
```

The rewrite tests cover course target parsing and origin protection, secret sanitization, multi-megabyte course content normalization, stable normalization of volatile Canvas URLs, compact comparison generation, duplicate-audit classification/reporting, Sunday-Saturday semester week numbering, unnumbered break weeks, convention-free date auditing, FERPA-safe module override capture, course-overview joins, and the convention-free course audit.

The Bash prototype tests remain under `tests/` while parity is being checked.

## Direction

The next major workflows are semester-rollover tools:

- richer at-a-glance course inventory and consistency checks
- date audit after Canvas import/shift
- break-aware schedule planning for Spring Break vs. Thanksgiving
- destination-course duplicate review and eventual cleanup plans
- explicit dry-run plans before any write operations

See [Canvas API TL;DR](docs/CANVAS_API_TLDR.md) for the API design notes and official references gathered during the prototype work.
