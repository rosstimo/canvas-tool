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

if [[ "$url" == *'page=2'* ]]; then
    printf 'HTTP/2 200\r\nContent-Type: application/json\r\n\r\n' >"$headers"
    printf '[{"id":3}]\n' >"$body"
else
    printf 'HTTP/2 200\r\nLink: <https://isu.instructure.com/api/v1/test?page=2&per_page=100>; rel="next"\r\nContent-Type: application/json\r\n\r\n' >"$headers"
    printf '[{"id":1},{"id":2}]\n' >"$body"
fi
printf '200'
MOCK
chmod +x "$TMP/bin/curl"

PATH="$TMP/bin:$PATH"
CANVAS_BASE_URL='https://isu.instructure.com'
CANVAS_API_TOKEN='test-only'
CANVAS_API_PER_PAGE=100
source "$ROOT/lib/canvas-course.sh"
source "$ROOT/lib/canvas-api.sh"

result="$(canvas_api_paginate '/api/v1/test')"
[[ "$(jq 'length' <<<"$result")" -eq 3 ]]
[[ "$(jq -r '.[2].id' <<<"$result")" == 3 ]]
printf 'PASS: pagination follows opaque next link and merges arrays\n'
