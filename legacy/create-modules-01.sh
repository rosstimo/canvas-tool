#!/bin/bash
# This script creates assignments in a Canvas course using the Canvas API.
CANVAS_BASE_URL="https://isu.instructure.com"
CANVAS_API_TOKEN="<REMOVED_CANVAS_API_TOKEN>"
COURSE_ID=3858
PUBLISH=true




for w in $(seq -w 1 16); do
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
