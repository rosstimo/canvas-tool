#!/usr/bin/env bash

canvas_origin_from_url() {
    local url="${1%/}"
    if [[ "$url" =~ ^(https://[^/]+) ]]; then
        printf '%s\n' "${BASH_REMATCH[1]}"
        return 0
    fi
    return 1
}

canvas_assert_same_origin() {
    local candidate="$1"
    local configured candidate_origin configured_origin

    configured="${CANVAS_BASE_URL%/}"
    candidate_origin="$(canvas_origin_from_url "$candidate")" || {
        printf 'Error: invalid Canvas URL: %s\n' "$candidate" >&2
        return 1
    }
    configured_origin="$(canvas_origin_from_url "$configured")" || {
        printf 'Error: invalid CANVAS_BASE_URL: %s\n' "$CANVAS_BASE_URL" >&2
        return 1
    }

    if [[ "$candidate_origin" != "$configured_origin" ]]; then
        printf 'Error: refusing to send Canvas credentials to %s; configured origin is %s\n' \
            "$candidate_origin" "$configured_origin" >&2
        return 1
    fi
}

canvas_resolve_course() {
    local target="$1"
    local configured="${CANVAS_BASE_URL%/}"

    CANVAS_COURSE_BASE_URL="$configured"
    CANVAS_COURSE_ID=""

    if [[ "$target" =~ ^[0-9]+$ ]]; then
        CANVAS_COURSE_ID="$target"
        return 0
    fi

    if [[ "$target" =~ ^(https://[^/]+)/courses/([0-9]+)([/\?#].*)?$ ]]; then
        CANVAS_COURSE_BASE_URL="${BASH_REMATCH[1]}"
        CANVAS_COURSE_ID="${BASH_REMATCH[2]}"
        canvas_assert_same_origin "$CANVAS_COURSE_BASE_URL"
        return $?
    fi

    printf 'Error: expected a numeric Canvas course ID or URL containing /courses/<id>: %s\n' "$target" >&2
    return 1
}

canvas_course_host() {
    local origin="$1"
    printf '%s\n' "${origin#https://}"
}
