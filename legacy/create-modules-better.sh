# Usage/help function
usage() {
  echo "Usage: $0 COURSE_ID [PUBLISH] [MODULE_START] [MODULE_END]"
  echo "  COURSE_ID: Canvas course ID (required)"
  echo "  PUBLISH: true or false (optional, default: false)"
  echo "  MODULE_START: first module number (optional, default: 1)"
  echo "  MODULE_END: last module number (optional, default: same as MODULE_START)"
  echo "Example: $0 3858 true 1 16"
}

#!/bin/bash

# This script creates assignments in a Canvas course using the Canvas API.

# Load environment variables from .env if it exists (for CANVAS_BASE_URL and CANVAS_API_TOKEN)
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi


# Parse command-line arguments
COURSE_ID="$1"
PUBLISH="$2"
MODULE_START="$3"
MODULE_END="$4"

if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
  usage
  exit 0
fi

# Set defaults if not provided
if [ -z "$COURSE_ID" ]; then
  usage
  exit 1
fi
if [ -z "$PUBLISH" ]; then
  PUBLISH=false
fi
if [ -z "$MODULE_START" ]; then
  MODULE_START=1
fi
if [ -z "$MODULE_END" ]; then
  MODULE_END=$MODULE_START
fi

# Ensure required .env variables are set
if [ -z "$CANVAS_BASE_URL" ] || [ -z "$CANVAS_API_TOKEN" ]; then
  echo "Error: CANVAS_BASE_URL and CANVAS_API_TOKEN must be set in .env file."
  exit 1
fi

for w in $(seq -w $MODULE_START $MODULE_END); do
  NAME="Week ${w}"
  echo "Creating $NAME"

  curl -sS -X POST \
    -H "Authorization: Bearer $CANVAS_API_TOKEN" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    "$CANVAS_BASE_URL/api/v1/courses/$COURSE_ID/modules" \
    --data-urlencode "module[name]=$NAME" \
    --data-urlencode "module[published]=$PUBLISH" \
  | jq -r '[.id, .name] | @tsv'

  sleep 0.2
done
