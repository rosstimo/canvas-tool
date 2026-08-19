#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export CANVAS_TOOLS_ROOT="$ROOT"

source "$ROOT/lib/canvas-recon.sh"

printf '{"default_view":"modules","apply_assignment_group_weights":false}\n' >"$TMP/course.json"
printf '{}\n' >"$TMP/settings.json"
for file in tabs modules module-items assignment-groups assignments classic-quizzes classic-quiz-questions new-quizzes new-quiz-items rubrics discussions announcements files folders features grading-standards outcome-links calendar-events; do
    printf '[]\n' >"$TMP/$file.json"
done

# Build a page body large enough that passing it through --argjson would exceed
# normal Linux argv limits. The normalizer must read it directly from the file.
printf '[{"title":"Large page","body":"' >"$TMP/pages.json"
head -c 3000000 /dev/zero | tr '\0' x >>"$TMP/pages.json"
printf '","published":true,"front_page":false}]\n' >>"$TMP/pages.json"

recon_normalize "$TMP"
jq -e '.pages[0].title == "Large page" and (.pages[0].body | length) == 3000000' \
    "$TMP/normalized.json" >/dev/null

printf 'PASS: multi-megabyte course content normalizes without argv expansion\n'
