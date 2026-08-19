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

The Python runtime currently has **no third-party runtime dependencies**. The standard library handles HTTP, JSON, configuration, dates, comparison, duplicate detection, HTML/reference inspection, and CLI parsing. `uv.lock` and `.python-version` keep development environments reproducible.

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
assignment-overrides.json
```

Module and assignment override snapshots deliberately do not retain specific student IDs or names. A student-targeted override is summarized only as a count.

## Comprehensive course audit

`canvas-tool audit COURSE` performs a fresh read-only recon and generates a **master audit plus specialized reports**. `course-overview.md` remains the at-a-glance course view; the audit suite goes much deeper without changing the overview format.

The master report is:

```text
comprehensive-audit.md
comprehensive-audit.json
```

It combines warnings/reviews from the specialized audits, the semester/date audit, and the duplicate-content audit. The master report also includes an API-coverage table so an unavailable endpoint is not mistaken for an empty Canvas feature.

Specialized reports currently include:

- `assignment-audit.md` - assignment groups, gradebook objects, points, grading type, due dates, submission types, module placement, peer review, and LTI/New Quiz classification
- `assignment-override-audit.md` - differentiated **Assign To** targets and override dates, with specific-student targets retained only as counts
- `module-audit.md` - module structure, prerequisites, completion requirements, publication state, item types, and captured content-reference integrity
- `quiz-audit.md` - Classic Quizzes, New Quizzes, quiz settings, question/item counts, question types, and bank-backed New Quiz entries
- `question-bank-audit.md` - Classic Question Banks and questions, Classic Quiz question groups/bank links, and New Quiz bank-backed items referenced by captured quizzes
- `grading-audit.md` - assignment-group weighting, rubrics, grading standards, learning outcomes, grading periods, and late policy
- `content-audit.md` - pages, files, folders, discussions, announcements, calendar events, and lightweight HTML/accessibility-review signals
- `link-audit.md` - stale or missing internal Canvas links, cross-course links, and an inventory of external-link domains
- `integration-audit.md` - navigation tabs, feature flags, external tools, LTI-backed assignments, module links, and LTI resource links
- `migration-audit.md` - course-copy/import history, migration issues, and content-export history
- `course-settings-audit.md` - course settings, sections, group categories/groups, blackout dates, and supporting course configuration

Existing reports are also part of the master view:

- `course-audit.md` - compact schedule/inventory exception report
- `date-audit.md` - detailed semester/date audit
- `duplicate-audit.md` - duplicate-content candidates
- `summary.md` - recon inventory
- `course-overview.md` - primary instructor-facing overview

Findings are intentionally conservative:

- **warning** means an objective structural/date conflict was detected
- **review** means the configuration deserves a look but may be intentional
- **observation** is inventory information and is not treated as an error

Examples of objective/review checks include dates outside the course or during configured breaks, invalid unlock/due/lock ordering, missing internal Canvas targets, empty question banks/quizzes/modules, inconsistent question counts, failed imports/exports, active migration issues, odd grade weighting, rubric associations, duplicate candidates, differentiated assignment targets, and lightweight HTML signals such as images without an `alt` attribute.

External URLs are inventoried but are not fetched by the audit. New Quiz item-bank reporting covers banks referenced by the captured quiz items; it does not claim to enumerate every item bank available to an instructor/account.

Every generated Markdown report in a course snapshot is automatically linked from:

```text
snapshots/<canvas-host>/<course-id>/README.md
```

Each report also gets a **Report index** backlink.

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

Recon intentionally avoids student rosters, enrollments, submissions, grades, quiz submissions, discussion entries, group memberships, and other student-level records. The default output remains:

```text
snapshots/<canvas-host>/<course-id>/
```

The expanded recon captures course/settings/navigation data plus modules, assignments, Classic/New Quizzes, Classic Question Banks, pages, rubrics, outcomes, files/folders, sections, groups/group categories without memberships, external tools/LTI links, grading periods/late policy, blackout/calendar dates, and content migration/export history where Canvas permits access.

Important files are:

- `README.md` - generated Markdown report index
- `summary.md` - human-readable recon inventory
- `manifest.json` - snapshot identity and capture metadata
- `normalized.json` - structural/content representation for cross-semester comparison
- `errors.json` - endpoints that were unavailable or denied
- the remaining JSON files - sanitized API responses for Canvas resource types

An unavailable endpoint is recorded rather than interpreted as an empty feature.

Generated snapshots and comparisons are ignored by Git.

## Duplicate audit

`canvas-tool duplicates COURSE` remains available as a separate specialized review tool. It audits normalized course content for duplicate candidates and does not modify Canvas. The comprehensive audit also runs this report automatically.

The duplicate heuristic uses names/content similarity. Its findings are review candidates only, especially the lower-confidence similar-name category.

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

The rewrite tests cover course target parsing and origin protection, secret sanitization, multi-megabyte course content normalization, stable normalization of volatile Canvas URLs, compact comparison generation, duplicate-audit classification/reporting, Sunday-Saturday semester week numbering, unnumbered break weeks, convention-free date auditing, FERPA-safe module and assignment override capture, course-overview joins, report indexing, New Quiz identification, question-bank audit generation, migration archaeology, stale internal-link detection, and the comprehensive audit rollup.

The Bash prototype tests remain under `tests/` while parity is being checked.

## Direction

The next major workflows are semester-rollover tools:

- richer cross-semester comparison using the expanded recon data
- date planning after Canvas import/shift
- break-aware schedule planning for Spring Break vs. Thanksgiving
- destination-course duplicate review and eventual cleanup plans
- explicit dry-run plans before any write operations

See [Canvas API TL;DR](docs/CANVAS_API_TLDR.md) for the API design notes and official references gathered during the prototype work.
