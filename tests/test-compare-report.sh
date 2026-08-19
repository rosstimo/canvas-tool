#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export CANVAS_TOOLS_ROOT="$TMP/work"
mkdir -p "$CANVAS_TOOLS_ROOT" "$TMP/a" "$TMP/b"
source "$ROOT/lib/canvas-recon.sh"

cat >"$TMP/a/manifest.json" <<'JSON'
{"course_id":"11657","course_name":"Spring course","course_code":"RCET2265-01-S26"}
JSON
cat >"$TMP/b/manifest.json" <<'JSON'
{"course_id":"18637","course_name":"Fall course","course_code":"RCET2265-01-F26"}
JSON

cat >"$TMP/a/normalized.json" <<'JSON'
{"assignments":[{"name":"A"}],"pages":[]}
JSON
cat >"$TMP/b/normalized.json" <<'JSON'
{"assignments":[{"name":"A"},{"name":"B"}],"pages":[{"title":"Intro"}]}
JSON

output="$(canvas_compare_snapshots "$TMP/a" "$TMP/b")"
printf '%s\n' "$output" | grep -q 'Changed areas:'
printf '%s\n' "$output" | grep -q 'assignments'
printf '%s\n' "$output" | grep -q 'pages'

summary="$(find "$CANVAS_TOOLS_ROOT/comparisons/11657-vs-18637" -name '*-summary.md' -print -quit)"
[[ -n "$summary" && -f "$summary" ]]
grep -q '^- A: \*\*Spring course\*\*' "$summary"
grep -q '^- B: \*\*Fall course\*\*' "$summary"

printf 'PASS: compact comparison report renders Markdown bullets safely\n'
