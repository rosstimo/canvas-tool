#!/usr/bin/env bash
set -euo pipefail

# Usage: ./make_time_mgmt_quizzes_tf.sh <COURSE_ID> <ASSIGNMENT_GROUP_ID> <WEEK1_DATE>
# Example: ./make_time_mgmt_quizzes_tf.sh 5040 16059 2025-09-01
# Notes:
# - WEEK1_DATE is the Monday that starts Week 1.
# - Times are computed in America/Denver and sent to Canvas as UTC ISO8601.

if [[ $# -ne 3 ]]; then
  echo "Usage: $0 <COURSE_ID> <ASSIGNMENT_GROUP_ID> <WEEK1_DATE_YYYY-MM-DD>" >&2
  exit 1
fi

COURSE_ID="$1"
ASSIGNMENT_GROUP_ID="$2"
WEEK1_DATE="$3"

# Load env
if [[ -f .env ]]; then
  # shellcheck source=/dev/null
  source .env
else
  echo ".env not found (needs CANVAS_BASE_URL, CANVAS_API_TOKEN)" >&2
  exit 1
fi

: "${CANVAS_BASE_URL:?missing}"
: "${CANVAS_API_TOKEN:?missing}"

AUTH=(-H "Authorization: Bearer ${CANVAS_API_TOKEN}")
JSONH=(-H "Content-Type: application/json")
BASE="${CANVAS_BASE_URL%/}"
TZ_LOCAL="America/Denver"

api() { curl -sS -X "$1" "${AUTH[@]}" "$BASE$2" "${@:3}"; }

# Convert local time (in TZ_LOCAL) to UTC ISO8601 Z
to_utc_iso() {
  local local_dt="$1"
  TZ="$TZ_LOCAL" date -d "$local_dt" -u +"%Y-%m-%dT%H:%M:%SZ"
}

# Create quiz and return JSON
create_quiz() {
  local title="$1"
  api POST "/api/v1/courses/${COURSE_ID}/quizzes" "${JSONH[@]}" \
    --data-binary @- <<EOF
{
  "quiz": {
    "title": "${title}",
    "description": "<p>${title}</p>",
    "quiz_type": "assignment",
    "assignment_group_id": ${ASSIGNMENT_GROUP_ID},
    "time_limit": 5,
    "shuffle_answers": false,
    "one_question_at_a_time": false,
    "allowed_attempts": 1,
    "show_correct_answers": false,
    "published": false
  }
}
EOF
}

# Add a True/False question worth 1 point; mark True as correct.
# Classic quizzes accept an answers array with answer_weight 100 for correct. :contentReference[oaicite:1]{index=1}
add_tf_question() {
  local quiz_id="$1"
  api POST "/api/v1/courses/${COURSE_ID}/quizzes/${quiz_id}/questions" "${JSONH[@]}" \
    --data-binary @- >/dev/null <<'EOF'
{
  "question": {
    "question_name": "Time Management Check",
    "question_text": "Did you complete all the required assignments by the due date?",
    "question_type": "true_false_question",
    "points_possible": 1,
    "answers": [
      {"answer_text": "True",  "answer_weight": 100},
      {"answer_text": "False", "answer_weight": 0}
    ]
  }
}
EOF
}

# Set availability via Assignments API on the backing assignment. :contentReference[oaicite:2]{index=2}
set_assignment_dates() {
  local assignment_id="$1"
  local unlock_iso="$2"
  local due_iso="$3"
  local lock_iso="$4"

  api PUT "/api/v1/courses/${COURSE_ID}/assignments/${assignment_id}" "${JSONH[@]}" \
    --data-binary @- >/dev/null <<EOF
{
  "assignment": {
    "unlock_at": "${unlock_iso}",
    "due_at":    "${due_iso}",
    "lock_at":   "${lock_iso}"
  }
}
EOF
}

# Loop W01..W16
for i in $(seq 0 15); do
  w=$(printf "%02d" $((i+1)))
  title="W${w}-Time Management"

  # compute week window in local time
  week_start_local="$(date -d "${WEEK1_DATE} +${i} week" +%Y-%m-%d) 00:00"
  week_end_sun_local="$(date -d "${WEEK1_DATE} +${i} week +6 day" +%Y-%m-%d) 22:30"

  unlock_at="$(to_utc_iso "${week_start_local}")"
  due_at="$(to_utc_iso "${week_end_sun_local}")"
  lock_at="${due_at}"  # same as due, locks at 10:30pm Sunday

  echo "Creating ${title} (unlock ${unlock_at}, due/lock ${due_at})"

  qjson="$(create_quiz "${title}")"
  quiz_id="$(jq -r '.id' <<<"$qjson")"
  assignment_id="$(jq -r '.assignment_id' <<<"$qjson")"

  if [[ -z "$quiz_id" || "$quiz_id" == "null" ]]; then
    echo "Failed to create ${title}"; jq . <<<"$qjson" >&2; exit 1
  fi

  add_tf_question "$quiz_id"
  set_assignment_dates "$assignment_id" "$unlock_at" "$due_at" "$lock_at"

  # chill slightly so Canvas doesn’t flip a table
  sleep 0.2
done

echo "All 16 quizzes created and dated. Try not to gloat in front of the class."
