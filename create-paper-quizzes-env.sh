#!/bin/bash
# This script creates assignments in a Canvas course using the Canvas API.

# Usage/help function
usage() {
  echo "Usage: $0 COURSE_ID GROUP_ID [POINTS] [PUBLISH]"
  echo "  COURSE_ID: Canvas course ID (required)"
  echo "  GROUP_ID: Assignment group ID (required)"
  echo "  POINTS: Points possible (optional, default: 100)"
  echo "  PUBLISH: true or false (optional, default: false)"
  echo "Example: $0 3858 17367 100 true"
}

# Load environment variables from .env if it exists (for CANVAS_BASE_URL and CANVAS_API_TOKEN)
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

# Parse command-line arguments
COURSE_ID="$1"
GROUP_ID="$2"
POINTS="$3"
PUBLISH="$4"

if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
  usage
  exit 0
fi

# Set defaults if not provided
if [ -z "$COURSE_ID" ] || [ -z "$GROUP_ID" ]; then
  usage
  exit 1
fi
if [ -z "$POINTS" ]; then
  POINTS=100
fi
if [ -z "$PUBLISH" ]; then
  PUBLISH=false
fi

# Ensure required .env variables are set
if [ -z "$CANVAS_BASE_URL" ] || [ -z "$CANVAS_API_TOKEN" ]; then
  echo "Error: CANVAS_BASE_URL and CANVAS_API_TOKEN must be set in .env file."
  exit 1
fi

for w in $(seq -w 01 16); do
  for q in $(seq -w 01 04); do
    NAME="W${w}-Quiz-${q}"
    echo "Creating $NAME"
    curl -sS -X POST \
      -H "Authorization: Bearer $CANVAS_API_TOKEN" \
      -H "Content-Type: application/json" \
      "$CANVAS_BASE_URL/api/v1/courses/$COURSE_ID/assignments" \
      -d "{\n        \"assignment\": {\n          \"name\": \"$NAME\",\n          \"submission_types\": [\"on_paper\"],\n          \"points_possible\": $POINTS,\n          \"assignment_group_id\": $GROUP_ID,\n          \"published\": $PUBLISH\n        }\n      }" | jq -r '.id, .name' 
    sleep 0.2
  done
done
