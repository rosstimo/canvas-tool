#!/bin/bash
# This script fetches an assignment from a Canvas course using the Canvas API.

# Usage/help function
usage() {
  echo "Usage: $0 COURSE_ID ASSIGNMENT_ID"
  echo "  COURSE_ID: Canvas course ID (required)"
  echo "  ASSIGNMENT_ID: Canvas assignment ID (required)"
  echo "  .env file must set CANVAS_BASE_URL and CANVAS_API_TOKEN"
  echo "Example: $0 5040 59227"
}

# Load environment variables from .env if it exists (for CANVAS_BASE_URL and CANVAS_API_TOKEN)
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

# Parse command-line arguments
COURSE_ID="$1"
ASSIGNMENT_ID="$2"

if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
  usage
  exit 0
fi

# Check for required parameters
if [ -z "$COURSE_ID" ] || [ -z "$ASSIGNMENT_ID" ]; then
  usage
  exit 1
fi

# Ensure required .env variables are set
if [ -z "$CANVAS_BASE_URL" ] || [ -z "$CANVAS_API_TOKEN" ]; then
  echo "Error: CANVAS_BASE_URL and CANVAS_API_TOKEN must be set in .env file."
  exit 1
fi

curl -sS -X GET \
  -H "Authorization: Bearer $CANVAS_API_TOKEN" \
  -H "Content-Type: application/json" \
  "$CANVAS_BASE_URL/api/v1/courses/$COURSE_ID/assignments/$ASSIGNMENT_ID"

