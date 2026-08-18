#!/usr/bin/env bash

# Locate the repository root from this file, not from the caller's cwd.
CANVAS_TOOLS_ROOT="$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &&
    pwd
)"

# Allow an alternate environment file when useful.
CANVAS_ENV_FILE="${CANVAS_ENV_FILE:-$CANVAS_TOOLS_ROOT/.env}"

if [[ ! -f "$CANVAS_ENV_FILE" ]]; then
    printf 'Error: Canvas environment file not found: %s\n' "$CANVAS_ENV_FILE" >&2
    printf 'Copy .env.example to .env and configure it first.\n' >&2
    return 1 2>/dev/null || exit 1
fi

# Export variables defined by .env.
set -a
# shellcheck disable=SC1090
source "$CANVAS_ENV_FILE"
set +a

if [[ -z "${CANVAS_BASE_URL:-}" ]]; then
    echo 'Error: CANVAS_BASE_URL is not set.' >&2
    return 1 2>/dev/null || exit 1
fi

if [[ -z "${CANVAS_API_TOKEN:-}" ]]; then
    echo 'Error: CANVAS_API_TOKEN is not set.' >&2
    return 1 2>/dev/null || exit 1
fi

# Normalize so scripts can safely append /api/v1/...
CANVAS_BASE_URL="${CANVAS_BASE_URL%/}"
