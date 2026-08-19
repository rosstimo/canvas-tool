#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CANVAS_BASE_URL='https://isu.instructure.com'
CANVAS_API_TOKEN='test-only'
source "$ROOT/lib/canvas-course.sh"

fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }
pass() { printf 'PASS: %s\n' "$1"; }

canvas_resolve_course 18637
[[ "$CANVAS_COURSE_BASE_URL" == 'https://isu.instructure.com' ]] || fail 'numeric base URL'
[[ "$CANVAS_COURSE_ID" == '18637' ]] || fail 'numeric course ID'
pass 'numeric course ID'

canvas_resolve_course 'https://isu.instructure.com/courses/18637'
[[ "$CANVAS_COURSE_ID" == '18637' ]] || fail 'course URL'
pass 'course URL'

canvas_resolve_course 'https://isu.instructure.com/courses/18637/modules'
[[ "$CANVAS_COURSE_ID" == '18637' ]] || fail 'deep course URL'
pass 'deep course URL'

canvas_resolve_course 'isu.instructure.com/courses/18637'
[[ "$CANVAS_COURSE_BASE_URL" == 'https://isu.instructure.com' ]] || fail 'scheme-less base URL'
[[ "$CANVAS_COURSE_ID" == '18637' ]] || fail 'scheme-less course ID'
pass 'scheme-less course URL'

canvas_resolve_course 'isu.instructure.com/courses/18637/modules'
[[ "$CANVAS_COURSE_ID" == '18637' ]] || fail 'deep scheme-less course URL'
pass 'deep scheme-less course URL'

if canvas_resolve_course 'https://example.com/courses/18637' >/dev/null 2>&1; then
    fail 'foreign origin accepted'
fi
pass 'foreign origin rejected'

if canvas_resolve_course 'example.com/courses/18637' >/dev/null 2>&1; then
    fail 'scheme-less foreign origin accepted'
fi
pass 'scheme-less foreign origin rejected'

if canvas_resolve_course 'RCET2265' >/dev/null 2>&1; then
    fail 'invalid target accepted'
fi
pass 'invalid target rejected'
