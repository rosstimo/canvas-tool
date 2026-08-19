# canvas-tool

A command-line tool for inspecting, comparing, auditing, and eventually managing Canvas LMS courses through the Canvas API.

## Python rewrite

Development has moved to Python 3.13 with `uv` for reproducible environments. The source checkout has a root launcher, so normal development use stays simple:

```bash
./canvas-tool doctor 18637
./canvas-tool courses RCET2265
./canvas-tool recon 18637
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

## Unified course audit

`canvas-tool audit COURSE` is the general read-only error-finding workflow. It performs one fresh recon, then combines:

- weekly module-structure checks
- date and schedule checks
- duplicate-content checks

The weekly structure audit recognizes deliberate week labels such as `W07`, `W7`, or `Week 7` and can flag:

- empty weekly modules
- duplicate week module numbers
- assignments whose declared week does not match the numbered module containing them
- assignment weeks for which no matching weekly module exists

The goal is to surface inconsistencies that are tedious to discover by clicking through the Canvas web interface. Findings are review prompts, not automatic repair instructions.

Results are written beside the snapshot as:

```text
course-audit.md
course-audit.json
date-audit.md
date-audit.json
duplicate-audit.md
duplicate-audit.json
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

`canvas-tool dates audit COURSE` performs a fresh read-only recon and checks Canvas dates against the matched semester calendar. The report uses:

- a compact `Week | Sunday-Saturday date range | Notes` semester reference
- `Week | Day | Date | Time` for assignment due dates
- the same `Week | Day | Date | Time` convention for module unlock dates
- flags for missing dates, dates during breaks/holidays, bad availability ordering, differentiated-date assignments, due-date clumps, strong due-time outliers, and mismatches between an assignment's `W##` title and its calculated semester week

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

`canvas-tool duplicates COURSE` performs a fresh read-only recon and audits normalized course content for duplicate candidates. It does not modify Canvas.

The audit distinguishes three categories:

- high-confidence candidates: same normalized name and same normalized content
- review items: same normalized name but different content
- similar-name candidates: lower-confidence names that are close enough to deserve inspection

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

The rewrite tests cover course target parsing and origin protection, secret sanitization, multi-megabyte course content normalization, stable normalization of volatile Canvas URLs, compact comparison generation, duplicate-audit classification/reporting, Sunday-Saturday semester week numbering, unnumbered break weeks, date-audit reporting, weekly module-structure checks, and the unified course audit.

The Bash prototype tests remain under `tests/` while parity is being checked.

## Direction

The next major workflows are semester-rollover tools:

- destination-course duplicate audit and eventual reviewed cleanup plans
- date audit after Canvas import/shift
- break-aware schedule planning for Spring Break vs. Thanksgiving
- explicit dry-run plans before any write operations

See [Canvas API TL;DR](docs/CANVAS_API_TLDR.md) for the API design notes and official references gathered during the prototype work.
