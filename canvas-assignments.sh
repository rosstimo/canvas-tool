#!/bin/bash

# Usage/help function
usage() {
  echo "Usage: $0 <CANVAS_COURSE_ID>"
  echo "  CANVAS_COURSE_ID: Canvas course ID (required)"
  echo "  .env file must set CANVAS_BASE_URL and CANVAS_API_TOKEN"
  echo "Example: $0 3858"
}

# This script creates a new assignment in a Canvas course using the Canvas API.
# Load environment variables from .env file
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
else
  echo ".env file not found!"
  exit 1
fi

# Check required environment variables
if [ -z "$CANVAS_BASE_URL" ] || [ -z "$CANVAS_API_TOKEN" ]; then
  echo "CANVAS_BASE_URL and CANVAS_API_TOKEN must be set in .env"
  exit 1
fi


# Show usage if -h or --help is passed
if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
  usage
  exit 0
fi

# Check for required course ID argument
if [ -z "$1" ]; then
  usage
  exit 1
fi
CANVAS_COURSE_ID="$1"

curl -sS -X GET \
  -H "Authorization: Bearer $CANVAS_API_TOKEN" \
  -H "Content-Type: application/json" \
  "$CANVAS_BASE_URL/api/v1/courses/$CANVAS_COURSE_ID/assignments" 

