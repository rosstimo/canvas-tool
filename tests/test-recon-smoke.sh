#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"

cat >"$TMP/bin/curl" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
headers=''
body=''
url=''
while (($#)); do
    case "$1" in
        -D) headers="$2"; shift 2 ;;
        -o) body="$2"; shift 2 ;;
        -w) shift 2 ;;
        -X|-H) shift 2 ;;
        -sS|-g) shift ;;
        *) url="$1"; shift ;;
    esac
done
printf 'HTTP/2 200\r\nContent-Type: application/json\r\n\r\n' >"$headers"
case "$url" in
    *'/api/v1/courses/18637?include'* )
        printf '{"id":18637,"name":"RCET Test","course_code":"RCETTEST","default_view":"modules","apply_assignment_group_weights":true,"grading_standard_id":null,"course_format":"on_campus"}\n' >"$body" ;;
    *'/api/v1/courses/18637/settings'* )
        printf '{"allow_student_discussion_topics":false}\n' >"$body" ;;
    *)
        printf '[]\n' >"$body" ;;
esac
printf '200'
MOCK
chmod +x "$TMP/bin/curl"

cat >"$ROOT/.env" <<'ENV'
CANVAS_BASE_URL=https://isu.instructure.com
CANVAS_API_TOKEN=test-only
ENV
trap 'rm -rf "$TMP"; rm -f "$ROOT/.env"; rm -rf "$ROOT/snapshots"' EXIT

PATH="$TMP/bin:$PATH" bash "$ROOT/bin/canvas-tool" recon 18637 >/dev/null
OUT="$ROOT/snapshots/isu.instructure.com/18637"
[[ -f "$OUT/manifest.json" ]]
[[ -f "$OUT/normalized.json" ]]
[[ -f "$OUT/summary.md" ]]
[[ "$(jq -r '.course_name' "$OUT/manifest.json")" == 'RCET Test' ]]
[[ "$(jq 'length' "$OUT/errors.json")" -eq 0 ]]
printf 'PASS: empty-course recon completes and builds snapshot artifacts\n'
