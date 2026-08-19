# canvas-tool

A command-line tool for inspecting, comparing, auditing, and eventually managing Canvas LMS courses through the Canvas API.

## Python rewrite

Development has moved to Python 3.13 with `uv` for reproducible environments. The source checkout has a root launcher, so normal development use stays simple:

```bash
./canvas-tool doctor 18637
./canvas-tool courses RCET2265
./canvas-tool recon 18637
./canvas-tool diff 11657 18637
```

The launcher runs the Python CLI through the repository's locked `uv` project. Direct `uv` use also works:

```bash
uv run canvas-tool doctor 18637
```

The Python runtime currently has **no third-party runtime dependencies**. The standard library handles HTTP, JSON, configuration, dates, and CLI parsing. `uv.lock` and `.python-version` keep development environments reproducible.

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
canvas-tool diff <course-a-id-or-url> <course-b-id-or-url>
canvas-tool api <METHOD> <path-or-url> [--paginate]
```

Course targets accept all of these forms:

```text
17600
isu.instructure.com/courses/17600
https://isu.instructure.com/courses/17600
```

A URL must match `CANVAS_BASE_URL` before credentials are sent.

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

## Tests

Python tests use the standard library and require no real Canvas token:

```bash
uv run python -m unittest discover -s tests_py -v
```

The initial rewrite tests cover course target parsing and origin protection, secret sanitization, multi-megabyte course content normalization, and compact comparison generation.

The Bash prototype tests remain under `tests/` while parity is being checked.

## Direction

The next major workflows are semester-rollover tools:

- destination-course audit for duplicate generated/imported modules and content
- date audit after Canvas import/shift
- break-aware schedule planning for Spring Break vs. Thanksgiving
- explicit dry-run plans before any write operations

See [Canvas API TL;DR](docs/CANVAS_API_TLDR.md) for the API design notes and official references gathered during the prototype work.
