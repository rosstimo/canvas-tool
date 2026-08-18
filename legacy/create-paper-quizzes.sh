#!/bin/bash
# This script creates assignments in a Canvas course using the Canvas API.
CANVAS_BASE_URL="https://isu.instructure.com"
CANVAS_API_TOKEN="<REMOVED_CANVAS_API_TOKEN>"
COURSE_ID=3858
GROUP_ID=17367
POINTS=100
PUBLISH=true

for w in $(seq -w 01 16); do
  for q in $(seq -w 01 04); do
    NAME="W${w}-Quiz-${q}"
    echo "Creating $NAME"
    curl -sS -X POST \
      -H "Authorization: Bearer $CANVAS_API_TOKEN" \
      -H "Content-Type: application/json" \
      "$CANVAS_BASE_URL/api/v1/courses/$COURSE_ID/assignments" \
      -d "{
        \"assignment\": {
          \"name\": \"$NAME\",
          \"submission_types\": [\"on_paper\"],
          \"points_possible\": $POINTS,
          \"assignment_group_id\": $GROUP_ID,
          \"published\": $PUBLISH
        }
      }" | jq -r '.id, .name' 
    sleep 0.2
  done
done

