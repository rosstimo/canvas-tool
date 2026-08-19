#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"

cat >"$TMP/test.env" <<'ENV'
CANVAS_BASE_URL=https://isu.instructure.com
CANVAS_API_TOKEN=test-only
ENV

cat >"$TMP/bin/curl" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
headers=''
body=''
while (($#)); do
    case "$1" in
        -D) headers="$2"; shift 2 ;;
        -o) body="$2"; shift 2 ;;
        -w) shift 2 ;;
        -X|-H) shift 2 ;;
        -sS|-g) shift ;;
        *) shift ;;
    esac
done
printf 'HTTP/2 200\r\nContent-Type: application/json\r\n\r\n' >"$headers"
cat >"$body" <<'JSON'
[
  {"id":18637,"name":"RCET 2265 Fall 2026","course_code":"RCET2265-01-F26","workflow_state":"available","term":{"name":"Fall 2026","end_at":"2026-12-20T00:00:00Z"}},
  {"id":15001,"name":"RCET 2265 Fall 2025","course_code":"RCET2265-01-F25","workflow_state":"completed","term":{"name":"Fall 2025","end_at":"2025-12-20T00:00:00Z"}},
  {"id":17600,"name":"RCET 3373 Fall 2026","course_code":"RCET3373-01-F26","workflow_state":"available","term":{"name":"Fall 2026","end_at":"2026-12-20T00:00:00Z"}}
]
JSON
printf '200'
MOCK
chmod +x "$TMP/bin/curl"

output="$(PATH="$TMP/bin:$PATH" CANVAS_ENV_FILE="$TMP/test.env" bash "$ROOT/bin/canvas-tool" courses RCET2265)"

grep -q $'18637\tRCET2265-01-F26' <<<"$output"
grep -q $'15001\tRCET2265-01-F25' <<<"$output"
if grep -q 'RCET3373' <<<"$output"; then
    echo 'FAIL: unrelated course was not filtered out' >&2
    exit 1
fi
printf 'PASS: course discovery includes historical matches and filters locally\n'
