# canvas-tool

A small command-line tool for inspecting, comparing, and eventually managing Canvas LMS courses through the Canvas API.

The current development branch provides a read-only course recon workflow plus a raw API escape hatch. Recon intentionally avoids student rosters, enrollments, submissions, grades, and discussion entries.

See [Canvas API TL;DR](docs/CANVAS_API_TLDR.md) for the design and official API references.

## Requirements

- Bash
- `curl`
- `jq`
- standard Unix tools (`awk`, `sed`, `find`, `diff`)

Copy `.env.example` to `.env` and set your Canvas token. `.env` is ignored by Git.

## First functional test

Use a normal Canvas course URL directly:

```bash
bash bin/canvas-tool doctor https://isu.instructure.com/courses/18637
```

Expected output is a series of `PASS` lines followed by the course name and course code. The URL supplies the Canvas origin and internal course ID; the origin must match `CANVAS_BASE_URL` before the bearer token is sent.

Then inspect the course identity and permissions:

```bash
bash bin/canvas-tool inspect https://isu.instructure.com/courses/18637
```

## Recon

```bash
bash bin/canvas-tool recon https://isu.instructure.com/courses/18637
```

A bare numeric ID works too:

```bash
bash bin/canvas-tool recon 18637
```

The default output is:

```text
snapshots/<canvas-host>/<course-id>/
```

Important files are:

- `summary.md` - quick human-readable inventory
- `manifest.json` - snapshot identity and capture metadata
- `normalized.json` - structural/content representation intended for cross-semester comparison
- `errors.json` - endpoints that were unavailable or denied
- the remaining JSON files - sanitized API responses for individual Canvas resource types

Generated snapshots are ignored by Git.

## Compare two courses

`diff` performs a fresh recon of both courses and compares their normalized forms:

```bash
bash bin/canvas-tool diff 18000 18637
```

Concrete Canvas object IDs and semester-specific dates are omitted from the normalized representation where practical so copied courses do not differ solely because Canvas assigned new IDs or the semester changed.

Comparison output is saved under `comparisons/`, which is also ignored by Git.

## Raw API access

For API work that does not deserve another one-off shell script:

```bash
bash bin/canvas-tool api GET /api/v1/courses/18637/assignment_groups
```

The same command can issue `POST`, `PUT`, `PATCH`, and `DELETE` requests when explicitly requested, with additional `curl` options passed after the endpoint. This is the low-level read/write escape hatch; the automated `doctor`, `inspect`, `recon`, and `diff` commands are read-only.

## Tests

The current tests do not require a real Canvas token:

```bash
bash tests/test-course-target.sh
bash tests/test-api-pagination.sh
bash tests/test-recon-smoke.sh
```

They cover URL/ID parsing and origin protection, Canvas pagination handling, and an end-to-end recon against a mocked API.
