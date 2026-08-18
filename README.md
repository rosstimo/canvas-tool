# canvas-tool

A small command-line tool for inspecting and managing Canvas LMS courses through the Canvas API.

The immediate goal is a safe, repeatable read-only workflow that can snapshot the current structure and content of a Canvas course without collecting student data. Those snapshots can then be compared with curriculum and planning repositories.

## Current work

The original repository contains a collection of Canvas API experiments. They are being preserved while a common CLI and API layer are built beside them.

See [Canvas API TL;DR](docs/CANVAS_API_TLDR.md) for the working design, official API references, snapshot scope, URL/ID handling, authentication rules, pagination, and cleanup plan.

Planned command shape:

```bash
canvas-tool snapshot https://isu.instructure.com/courses/18637
canvas-tool snapshot 18637
```

The full course URL can provide both the Canvas origin and internal course ID. A bare course ID uses `CANVAS_BASE_URL` from `.env`.
