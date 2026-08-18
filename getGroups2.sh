#!/usr/bin/env bash
set -e
set -a; source .env; set +a  # needs CANVAS_BASE_URL, CANVAS_API_TOKEN
course_id="$1"
curl -sS -H "Authorization: Bearer ${CANVAS_API_TOKEN}" \
  "${CANVAS_BASE_URL%/}/api/v1/courses/5040/assignment_groups/" | jq .
