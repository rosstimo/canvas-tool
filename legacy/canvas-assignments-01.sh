#!/bin/bash
# This script creates a new assignment in a Canvas course using the Canvas API.
CANVAS_BASE_URL="https://isu.instructure.com"
CANVAS_API_TOKEN="<REMOVED_CANVAS_API_TOKEN>"
CANVAS_COURSE_ID="5040"



curl -sS -X GET \
  -H "Authorization: Bearer $CANVAS_API_TOKEN" \
  -H "Content-Type: application/json" \
  "$CANVAS_BASE_URL/api/v1/courses/5040/assignments" 

