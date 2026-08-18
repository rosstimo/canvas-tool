# Canvas API TL;DR for `canvas-tool`

This document is the working technical reference for turning the old Canvas API experiments in this repository into one predictable, reusable command-line tool.

The design goal is simple: make it easy to point the tool at a Canvas course, capture the current course state without student data, and produce a snapshot that can be compared with curriculum/planning repositories.

## 1. The Canvas course URL already gives us what we need

A normal Canvas course URL such as:

```text
https://isu.instructure.com/courses/18637
```

contains:

```text
Canvas base URL: https://isu.instructure.com
Canvas course ID: 18637
```

`18637` is the Canvas internal course ID. It is not the same thing as a human-facing course code such as `RCET2265`, and it is not necessarily the SIS course ID.

Canvas exposes a single course at:

```text
GET /api/v1/courses/:id
```

Canvas also supports SIS IDs in many API paths with the `sis_course_id:` prefix.

### Input rule for this tool

The CLI should accept either form:

```bash
canvas-tool snapshot https://isu.instructure.com/courses/18637
canvas-tool snapshot 18637
```

When given a full URL, the tool should extract the scheme/host and the numeric ID from `/courses/<id>`.

When given only an ID, it should use `CANVAS_BASE_URL` from `.env`.

The parser should also tolerate a deeper course URL such as:

```text
https://isu.instructure.com/courses/18637/modules
https://isu.instructure.com/courses/18637/assignments/12345
```

because the `/courses/<id>` portion still uniquely identifies the course context.

### Security rule

A supplied URL must not cause the tool to send the Canvas bearer token to an arbitrary host.

If `.env` defines:

```text
CANVAS_BASE_URL=https://isu.instructure.com
```

then a supplied course URL should normally be required to use that same origin before an authenticated API request is made. This prevents an accidental or malicious URL from redirecting the bearer token to another server.

## 2. Authentication

For this local CLI, `.env` is the right place for the manually generated Canvas access token:

```dotenv
CANVAS_BASE_URL=https://isu.instructure.com
CANVAS_API_TOKEN=...
```

`.env` must stay ignored by Git. `.env.example` must contain placeholders only.

Authenticated requests should use HTTPS and the HTTP authorization header:

```text
Authorization: Bearer <token>
```

The token should never be placed in a URL or query string. Canvas supports query-string tokens, but the official documentation discourages them because they are easier to leak through logs and other intermediaries.

Official documentation:

- Canvas API overview: https://developerdocs.instructure.com/services/canvas
- OAuth2 and access tokens: https://canvas.instructure.com/doc/api/file.oauth.html

## 3. One shared API layer

Legacy scripts currently repeat `.env` loading, `curl`, headers, and error handling. New code should centralize this.

Suggested split:

```text
bin/canvas-tool
lib/canvas-env.sh
lib/canvas-api.sh
```

`canvas-env.sh` should own configuration loading and validation.

`canvas-api.sh` should own:

- authenticated requests
- URL construction
- HTTP status handling
- JSON validation
- pagination
- rate-limit handling
- consistent diagnostics

Every command should call this API layer instead of invoking `curl` independently.

## 4. Pagination is mandatory

Canvas collection endpoints are paginated. The default page size is 10 items.

The tool must not assume that `per_page=100` means there are no more results. Canvas explicitly says callers should follow the HTTP `Link` header, and the pagination URLs should be treated as opaque.

That means every list operation should effectively do:

```text
request first page
append JSON objects
follow rel="next"
repeat until there is no next link
```

Official documentation:

- Pagination: https://developerdocs.instructure.com/services/canvas/basics/file.pagination

## 5. Rate limiting

Canvas uses dynamic request-cost throttling. API responses can include:

```text
X-Request-Cost
X-Rate-Limit-Remaining
```

A throttled request can return HTTP 429. The tool should perform requests serially by default and have a bounded retry/backoff path for 429 responses.

This is another reason the old `sleep 0.2` approach should disappear from new code. Rate handling belongs in the common API layer.

Official documentation:

- Throttling: https://developerdocs.instructure.com/services/canvas/basics/file.throttling

## 6. IDs

Canvas normally uses internal object IDs. It also supports SIS identifiers on many endpoints.

For example:

```text
/api/v1/courses/18637/assignments
```

uses the Canvas internal course ID, while:

```text
/api/v1/courses/sis_course_id:SOME-SIS-ID/assignments
```

uses a SIS course ID.

For our initial tool, the Canvas internal numeric ID is the canonical identifier because it falls naturally out of the browser URL.

Official documentation:

- Object IDs and SIS IDs: https://developerdocs.instructure.com/services/canvas/basics/file.object_ids
- Courses API: https://developerdocs.instructure.com/services/canvas/resources/courses

## 7. Snapshot scope

The first useful product should be a course-content snapshot, not a full LMS backup.

A default snapshot should capture enough information to understand what the course really looks like without collecting student records.

Suggested initial scope:

### Course

```text
GET /api/v1/courses/:id
GET /api/v1/courses/:course_id/settings
```

Capture course identity, code, dates, syllabus/settings that affect course behavior, and whether assignment-group weighting is in use.

Official documentation:

- Courses: https://developerdocs.instructure.com/services/canvas/resources/courses

### Navigation tabs

```text
GET /api/v1/courses/:course_id/tabs
```

This records which Canvas navigation entries are visible/hidden and their order.

Official documentation:

- Tabs: https://developerdocs.instructure.com/services/canvas/resources/tabs

### Modules and module items

```text
GET /api/v1/courses/:course_id/modules
```

Use `include[]=items` and `include[]=content_details` when useful, but do not assume Canvas will always inline every item. The official API explicitly allows Canvas to omit inline items when there are too many, so the tool must be able to fall back to the module-items endpoint.

This is one of the most important parts of the snapshot because modules represent the actual learning sequence students see.

Official documentation:

- Modules: https://developerdocs.instructure.com/services/canvas/resources/modules

### Assignment groups

Assignment groups are needed to understand grouping and grade weighting.

Official documentation:

- Assignment Groups: https://developerdocs.instructure.com/services/canvas/resources/assignment_groups

### Assignments

```text
GET /api/v1/courses/:course_id/assignments
```

Capture names, IDs, descriptions, points, submission types, assignment-group membership, base due/unlock/lock dates, publication state, position, and other course-design metadata.

Do not include submissions or student visibility data by default.

Official documentation:

- Assignments: https://developerdocs.instructure.com/services/canvas/resources/assignments

### Classic Quizzes

```text
GET /api/v1/courses/:course_id/quizzes
```

Classic Quizzes use the normal `/api/v1` namespace.

Official documentation:

- Quizzes: https://developerdocs.instructure.com/services/canvas/resources/quizzes

### New Quizzes

New Quizzes are separate and use a different API namespace:

```text
GET /api/quiz/v1/courses/:course_id/quizzes
```

The New Quiz API identifies individual new quizzes by their associated assignment ID in several endpoints. We should support both Classic and New Quizzes rather than assuming one quiz system.

Official documentation:

- New Quizzes: https://developerdocs.instructure.com/services/canvas/resources/new_quizzes

### Pages

Capture the page index and, for a full content snapshot, retrieve individual page bodies.

Pages have both an integer `page_id` and a URL-style page identifier, so page handling should use the documented semantics rather than assuming every page locator is simply an integer.

Official documentation:

- Pages: https://developerdocs.instructure.com/services/canvas/resources/pages

### Rubrics

Rubrics are useful for curriculum alignment and should be included in the content snapshot.

```text
GET /api/v1/courses/:course_id/rubrics
```

Do not include rubric assessments, because those are grading/student data.

Official documentation:

- Rubrics: https://developerdocs.instructure.com/services/canvas/resources/rubrics

### Files

Initially capture file metadata, not the binary file contents.

```text
GET /api/v1/courses/:course_id/files
```

Metadata lets us see what supporting material exists without turning a structural snapshot into a large file backup.

Official documentation:

- Files: https://developerdocs.instructure.com/services/canvas/resources/files

## 8. Privacy boundary

Default snapshots should avoid FERPA-sensitive/student-specific data.

Do not fetch by default:

- course users or enrollments
- student names or IDs
- submissions
- grades or scores
- rubric assessments
- quiz submissions/results
- analytics tied to users
- discussion participation tied to users
- student-specific assignment visibility

The snapshot is intended to describe the course design and content, not student performance.

A future command may explicitly collect additional instructor-only data when there is a clear use case, but that should be opt-in and stored separately.

## 9. Snapshot output

A snapshot should contain both machine-readable data and a concise human-readable summary.

Suggested structure:

```text
snapshots/
└── isu.instructure.com/
    └── 18637/
        ├── manifest.json
        ├── course.json
        ├── settings.json
        ├── tabs.json
        ├── modules.json
        ├── assignment-groups.json
        ├── assignments.json
        ├── classic-quizzes.json
        ├── new-quizzes.json
        ├── pages.json
        ├── rubrics.json
        ├── files.json
        └── summary.md
```

`manifest.json` should record at least:

- source Canvas origin
- course ID
- canonical browser URL
- snapshot timestamp
- tool version/commit when practical
- which endpoints succeeded or failed

Snapshots should remain ignored by Git by default until we have a deliberate policy for sanitized curriculum snapshots.

## 10. Useful command shape

The eventual user-facing interface should be small.

Examples:

```bash
canvas-tool snapshot https://isu.instructure.com/courses/18637
canvas-tool snapshot 18637
canvas-tool inspect https://isu.instructure.com/courses/18637
canvas-tool api GET /api/v1/courses/18637/modules
```

The raw `api` command would preserve the usefulness of the old experimental scripts without requiring a new shell script every time we want to try one endpoint.

Later, curriculum comparison can build on the stable snapshot format:

```bash
canvas-tool compare https://isu.instructure.com/courses/18637 ../RCET2265-planning
```

The compare feature can evolve independently from Canvas fetching because it consumes a snapshot rather than making ad-hoc API calls.

## 11. Legacy-script cleanup strategy

The sanitized baseline commit preserves the old experiments, so there is no reason to keep polishing duplicates.

Recommended migration:

1. Build the new CLI and shared API layer beside the old scripts.
2. Implement read-only commands first.
3. Implement `snapshot` and verify it against real courses.
4. Move old scripts under `legacy/` once their useful behavior is represented by the new tool.
5. Add write operations only after the read/snapshot layer is dependable.
6. Eventually delete legacy scripts when Git history is sufficient for archaeology.

Read-only first is intentional. Fetching and comparing course state is lower risk than creating or editing assignments/modules while the tool is still taking shape.

## 12. Official Canvas API references

Primary references for this project:

- API overview: https://developerdocs.instructure.com/services/canvas
- Courses: https://developerdocs.instructure.com/services/canvas/resources/courses
- Object/SIS IDs: https://developerdocs.instructure.com/services/canvas/basics/file.object_ids
- Pagination: https://developerdocs.instructure.com/services/canvas/basics/file.pagination
- Throttling: https://developerdocs.instructure.com/services/canvas/basics/file.throttling
- Modules: https://developerdocs.instructure.com/services/canvas/resources/modules
- Assignment Groups: https://developerdocs.instructure.com/services/canvas/resources/assignment_groups
- Assignments: https://developerdocs.instructure.com/services/canvas/resources/assignments
- Classic Quizzes: https://developerdocs.instructure.com/services/canvas/resources/quizzes
- New Quizzes: https://developerdocs.instructure.com/services/canvas/resources/new_quizzes
- Pages: https://developerdocs.instructure.com/services/canvas/resources/pages
- Rubrics: https://developerdocs.instructure.com/services/canvas/resources/rubrics
- Files: https://developerdocs.instructure.com/services/canvas/resources/files
- Tabs: https://developerdocs.instructure.com/services/canvas/resources/tabs
- OAuth2/token handling: https://canvas.instructure.com/doc/api/file.oauth.html

The Instructure developer portal is now the preferred home for API documentation. The older `canvas.instructure.com/doc/api` pages are being redirected/migrated to the developer portal, so new project documentation should prefer `developerdocs.instructure.com` links where an equivalent page exists.
