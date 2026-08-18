#!/usr/bin/env bash

CANVAS_API_MAX_RETRIES="${CANVAS_API_MAX_RETRIES:-4}"
CANVAS_API_PER_PAGE="${CANVAS_API_PER_PAGE:-100}"

canvas_api_url() {
    local target="$1"

    if [[ "$target" =~ ^https:// ]]; then
        canvas_assert_same_origin "$target" || return 1
        printf '%s\n' "$target"
    elif [[ "$target" == /* ]]; then
        printf '%s%s\n' "${CANVAS_BASE_URL%/}" "$target"
    else
        printf '%s/%s\n' "${CANVAS_BASE_URL%/}" "$target"
    fi
}

canvas_api_fetch_to_files() {
    local method="$1"
    local target="$2"
    local headers_file="$3"
    local body_file="$4"
    shift 4

    local url status attempt=0 delay=1
    url="$(canvas_api_url "$target")" || return 1

    while :; do
        : >"$headers_file"
        : >"$body_file"

        if ! status="$(curl -sS -g \
            -D "$headers_file" \
            -o "$body_file" \
            -w '%{http_code}' \
            -X "$method" \
            -H "Authorization: Bearer ${CANVAS_API_TOKEN}" \
            -H 'Accept: application/json' \
            "$@" \
            "$url")"; then
            printf 'Error: curl failed for %s %s\n' "$method" "$url" >&2
            return 1
        fi

        if [[ "$status" =~ ^2[0-9][0-9]$ ]]; then
            return 0
        fi

        if [[ "$status" == "429" || "$status" == "500" || "$status" == "502" || "$status" == "503" || "$status" == "504" ]]; then
            if (( attempt < CANVAS_API_MAX_RETRIES )); then
                attempt=$((attempt + 1))
                printf 'Canvas API returned HTTP %s; retry %d/%d in %ss\n' \
                    "$status" "$attempt" "$CANVAS_API_MAX_RETRIES" "$delay" >&2
                sleep "$delay"
                delay=$((delay * 2))
                continue
            fi
        fi

        printf 'Canvas API error: HTTP %s for %s %s\n' "$status" "$method" "$url" >&2
        if jq -e . "$body_file" >/dev/null 2>&1; then
            jq . "$body_file" >&2
        else
            sed -n '1,20p' "$body_file" >&2
        fi
        return 22
    done
}

canvas_api_request() {
    local method="$1"
    local target="$2"
    shift 2

    local tmpdir headers body
    tmpdir="$(mktemp -d)"
    headers="$tmpdir/headers"
    body="$tmpdir/body"

    if canvas_api_fetch_to_files "$method" "$target" "$headers" "$body" "$@"; then
        cat "$body"
        rm -rf "$tmpdir"
        return 0
    else
        local rc=$?
        rm -rf "$tmpdir"
        return "$rc"
    fi
}

canvas_api_next_link() {
    local headers_file="$1"

    tr -d '\r' <"$headers_file" | awk '
        tolower($0) ~ /^link:/ {
            sub(/^[^:]*:[[:space:]]*/, "")
            count=split($0, parts, ",")
            for (i=1; i<=count; i++) {
                if (parts[i] ~ /rel="next"/) {
                    if (match(parts[i], /<[^>]+>/)) {
                        print substr(parts[i], RSTART+1, RLENGTH-2)
                        exit
                    }
                }
            }
        }
    '
}

canvas_api_paginate() {
    local target="$1"
    local url tmpdir headers body next accumulator merged

    url="$(canvas_api_url "$target")" || return 1
    if [[ "$url" != *"per_page="* ]]; then
        if [[ "$url" == *\?* ]]; then
            url="${url}&per_page=${CANVAS_API_PER_PAGE}"
        else
            url="${url}?per_page=${CANVAS_API_PER_PAGE}"
        fi
    fi

    tmpdir="$(mktemp -d)"
    headers="$tmpdir/headers"
    body="$tmpdir/body"
    accumulator="$tmpdir/all.json"
    printf '[]\n' >"$accumulator"

    while [[ -n "$url" ]]; do
        if canvas_api_fetch_to_files GET "$url" "$headers" "$body"; then
            :
        else
            local rc=$?
            rm -rf "$tmpdir"
            return "$rc"
        fi

        if ! jq -e 'type == "array"' "$body" >/dev/null 2>&1; then
            printf 'Error: expected an array from paginated endpoint: %s\n' "$url" >&2
            jq . "$body" >&2 2>/dev/null || true
            rm -rf "$tmpdir"
            return 1
        fi

        merged="$tmpdir/merged.json"
        jq -s '.[0] + .[1]' "$accumulator" "$body" >"$merged"
        mv "$merged" "$accumulator"

        next="$(canvas_api_next_link "$headers")"
        if [[ -n "$next" ]]; then
            canvas_assert_same_origin "$next" || {
                rm -rf "$tmpdir"
                return 1
            }
        fi
        url="$next"
    done

    cat "$accumulator"
    rm -rf "$tmpdir"
}
