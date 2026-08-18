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
        printf '{"id":18637,"name":"RCET Test","course_code":"RCETTEST","default_view":"modules","apply_assignment_group_weights":true,"grading_standard_id":null,"course_format":"on_campus","syllabus_body":"<p>Test syllabus</p>"}\n' >"$body" ;;
    *'/api/v1/courses/18637/settings'* )
        printf '{"allow_student_discussion_topics":false}\n' >"$body" ;;
    *'/api/quiz/v1/courses/18637/quizzes?per_page=100'* )
        printf '[{"id":"77","title":"New Quiz","points_possible":10,"published":true,"quiz_settings":{"student_access_code":"DO-NOT-LEAK","shuffle_answers":true}}]\n' >"$body" ;;
    *'/api/quiz/v1/courses/18637/quizzes/77/items?per_page=100'* )
        printf '[{"id":"1","position":1,"points_possible":1,"entry_type":"Item","entry":{"item_body":"Question?"}}]\n' >"$body" ;;
    *)
        printf '[]\n' >"$body" ;;
esac
printf '200'
MOCK
chmod +x "$TMP/bin/curl"

cat >"$TMP/test.env" <<'ENV'
CANVAS_BASE_URL=https://isu.instructure.com
CANVAS_API_TOKEN=test-only
ENV

OUT="$TMP/snapshot"
PATH="$TMP/bin:$PATH" CANVAS_ENV_FILE="$TMP/test.env" \
    bash "$ROOT/bin/canvas-tool" recon 18637 "$OUT" >/dev/null

[[ -f "$OUT/manifest.json" ]]
[[ -f "$OUT/normalized.json" ]]
[[ -f "$OUT/summary.md" ]]
[[ "$(jq -r '.course_name' "$OUT/manifest.json")" == 'RCET Test' ]]
[[ "$(jq 'length' "$OUT/errors.json")" -eq 0 ]]
[[ "$(jq 'length' "$OUT/new-quiz-items.json")" -eq 1 ]]
if rg -F 'DO-NOT-LEAK' "$OUT" >/dev/null; then
    printf 'FAIL: recon retained a New Quiz access code\n' >&2
    exit 1
fi
printf 'PASS: recon completes, captures New Quiz items, and strips access codes\n'
