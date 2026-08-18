#!/usr/bin/env bash

recon_error() {
    local file="$1" name="$2" endpoint="$3" tmp="${file}.tmp"
    jq --arg name "$name" --arg endpoint "$endpoint" '.+[{name:$name,endpoint:$endpoint}]' "$file" >"$tmp"
    mv "$tmp" "$file"
}

recon_get() {
    local out="$1" errors="$2" name="$3" endpoint="$4" mode="$5"
    printf '  %-28s' "$name" >&2
    if [[ "$mode" == collection ]]; then
        if canvas_api_paginate "$endpoint" | jq . >"$out/$name.json"; then
            printf '%s items\n' "$(jq length "$out/$name.json")" >&2; return 0
        fi
        printf '[]\n' >"$out/$name.json"
    else
        if canvas_api_request GET "$endpoint" | jq . >"$out/$name.json"; then
            printf 'ok\n' >&2; return 0
        fi
        printf '{}\n' >"$out/$name.json"
    fi
    recon_error "$errors" "$name" "$endpoint"
    printf 'unavailable\n' >&2
}

# Expand an index into full objects or child collections.
# row_filter must emit TSV: id, title, optional position.
recon_expand() {
    local out="$1" errors="$2" name="$3" index="$4" row_filter="$5" template="$6" mode="$7" shape="$8"
    local result="$out/$name.json" tmpdir id title position endpoint data next
    tmpdir="$(mktemp -d)"; printf '[]\n' >"$result"
    printf '  %-28s' "$name" >&2
    while IFS=$'\t' read -r id title position; do
        [[ -n "$id" ]] || continue
        endpoint="${template//\{id\}/$id}"
        if [[ "$mode" == collection ]]; then
            data="$(canvas_api_paginate "$endpoint")" || { recon_error "$errors" "$name:$id" "$endpoint"; continue; }
        else
            data="$(canvas_api_request GET "$endpoint")" || { recon_error "$errors" "$name:$id" "$endpoint"; continue; }
        fi
        next="$tmpdir/next.json"
        if [[ "$shape" == flat ]]; then
            jq --argjson data "$data" '.+[$data]' "$result" >"$next"
        else
            jq --arg source_id "$id" --arg title "$title" --arg source_position "${position:-}" --argjson items "$data" \
              '.+[{source_id:$source_id,title:$title,source_position:($source_position|tonumber? // null),items:$items}]' "$result" >"$next"
        fi
        mv "$next" "$result"
    done < <(jq -r "$row_filter | @tsv" "$index")
    printf '%s records\n' "$(jq length "$result")" >&2
    rm -rf "$tmpdir"
}

recon_sanitize() {
    local out="$1"
    find "$out" -maxdepth 1 -type f -name '*.json' ! -name manifest.json ! -name normalized.json -print0 |
    while IFS= read -r -d '' file; do
        jq 'walk(if type=="object" then
          del(.access_code,.secure_params,.submissions_download_url,.speed_grader_url,
              .message_students_url,.quiz_submissions_url,.quiz_statistics_url,.quiz_reports_url,
              .quiz_submission_versions_html_url,.mobile_url,.preview_url,.thumbnail_url,
              .author,.user,.participants,.lockdown_browser_monitor_data,.ip_filter,.ics) |
          if (has("filename") and has("folder_id")) then del(.url) else . end
        else . end)' "$file" >"$file.tmp" && mv "$file.tmp" "$file"
    done
}

recon_normalize() {
    local out="$1"
    jq -n \
      --argjson course "$(cat "$out/course.json")" \
      --argjson settings "$(cat "$out/settings.json")" \
      --argjson tabs "$(cat "$out/tabs.json")" \
      --argjson module_items "$(cat "$out/module-items.json")" \
      --argjson groups "$(cat "$out/assignment-groups.json")" \
      --argjson assignments "$(cat "$out/assignments.json")" \
      --argjson classic_quizzes "$(cat "$out/classic-quizzes.json")" \
      --argjson classic_questions "$(cat "$out/classic-quiz-questions.json")" \
      --argjson new_quizzes "$(cat "$out/new-quizzes.json")" \
      --argjson new_items "$(cat "$out/new-quiz-items.json")" \
      --argjson pages "$(cat "$out/pages.json")" \
      --argjson rubrics "$(cat "$out/rubrics.json")" \
      --argjson discussions "$(cat "$out/discussions.json")" \
      --argjson announcements "$(cat "$out/announcements.json")" \
      --argjson files "$(cat "$out/files.json")" \
      --argjson folders "$(cat "$out/folders.json")" \
      --argjson features "$(cat "$out/features.json")" \
      --argjson grading_standards "$(cat "$out/grading-standards.json")" \
      --argjson outcome_links "$(cat "$out/outcome-links.json")" \
      --argjson calendar_events "$(cat "$out/calendar-events.json")" \
      -f "$CANVAS_TOOLS_ROOT/lib/canvas-normalize.jq" >"$out/normalized.json"
}

recon_summary() {
    local out="$1" m="$out/manifest.json" e="$out/errors.json"
    {
      printf '# Canvas course recon\n\n- Course: **%s**\n- Course code: `%s`\n- Canvas course ID: `%s`\n- Canvas origin: `%s`\n- Captured: `%s`\n\n' \
        "$(jq -r .course_name "$m")" "$(jq -r '.course_code // ""' "$m")" "$(jq -r .course_id "$m")" \
        "$(jq -r .base_url "$m")" "$(jq -r .captured_at "$m")"
      printf '## Counts\n\n| Resource | Count |\n|---|---:|\n'
      for spec in 'Modules:modules' 'Assignments:assignments' 'Assignment groups:assignment-groups' \
        'Classic quizzes:classic-quizzes' 'New quizzes:new-quizzes' 'Pages:pages' 'Rubrics:rubrics' \
        'Discussions:discussions' 'Announcements:announcements' 'Files:files' 'Sections:sections' \
        'Grading standards:grading-standards' 'Outcome links:outcome-links' 'Calendar events:calendar-events'; do
          printf '| %s | %s |\n' "${spec%%:*}" "$(jq length "$out/${spec#*:}.json")"
      done
      printf '\n## Notes\n\n`normalized.json` omits Canvas object IDs and concrete semester dates where practical so copied courses can be compared with less noise. Other JSON files contain sanitized API results. Student rosters, enrollments, submissions, grades, and discussion entries are not requested.\n\n'
      if [[ "$(jq length "$e")" -eq 0 ]]; then printf 'All requested resources were retrieved successfully.\n';
      else printf 'Unavailable resources are listed in `errors.json`.\n'; fi
    } >"$out/summary.md"
}

canvas_recon() {
    local target="$1" requested="${2:-}" host out errors course id name code captured
    canvas_resolve_course "$target" || return 1
    id="$CANVAS_COURSE_ID"; host="$(canvas_course_host "$CANVAS_COURSE_BASE_URL")"
    out="${requested:-$CANVAS_TOOLS_ROOT/snapshots/$host/$id}"
    mkdir -p "$out"; errors="$out/errors.json"; printf '[]\n' >"$errors"
    printf 'Recon: %s (course %s)\n' "$CANVAS_COURSE_BASE_URL" "$id" >&2

    course="$(canvas_api_request GET "/api/v1/courses/$id?include[]=permissions&include[]=term&include[]=syllabus_body")" || return 1
    jq . <<<"$course" >"$out/course.json"
    name="$(jq -r '.name // "unnamed course"' "$out/course.json")"; code="$(jq -r '.course_code // ""' "$out/course.json")"
    captured="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
    jq -n --arg captured_at "$captured" --arg base_url "$CANVAS_COURSE_BASE_URL" --arg course_id "$id" \
      --arg course_name "$name" --arg course_code "$code" \
      '{schema_version:1,captured_at:$captured_at,base_url:$base_url,course_id:$course_id,course_name:$course_name,course_code:$course_code,student_data_included:false}' >"$out/manifest.json"

    recon_get "$out" "$errors" settings "/api/v1/courses/$id/settings" single
    recon_get "$out" "$errors" tabs "/api/v1/courses/$id/tabs" collection
    recon_get "$out" "$errors" modules "/api/v1/courses/$id/modules" collection
    recon_expand "$out" "$errors" module-items "$out/modules.json" '.[]|[.id,.name,.position]' "/api/v1/courses/$id/modules/{id}/items?include[]=content_details" collection group
    recon_get "$out" "$errors" assignment-groups "/api/v1/courses/$id/assignment_groups" collection
    recon_get "$out" "$errors" assignments "/api/v1/courses/$id/assignments" collection
    recon_get "$out" "$errors" classic-quizzes "/api/v1/courses/$id/quizzes" collection
    recon_expand "$out" "$errors" classic-quiz-questions "$out/classic-quizzes.json" '.[]|[.id,.title]' "/api/v1/courses/$id/quizzes/{id}/questions" collection group
    recon_get "$out" "$errors" new-quizzes "/api/quiz/v1/courses/$id/quizzes" collection
    recon_expand "$out" "$errors" new-quiz-items "$out/new-quizzes.json" '.[]|[.id,.title]' "/api/quiz/v1/courses/$id/quizzes/{id}/items" collection group
    recon_get "$out" "$errors" pages-index "/api/v1/courses/$id/pages" collection
    recon_expand "$out" "$errors" pages "$out/pages-index.json" '.[]|[.page_id,.title]' "/api/v1/courses/$id/pages/page_id:{id}" single flat
    recon_get "$out" "$errors" rubrics-index "/api/v1/courses/$id/rubrics" collection
    recon_expand "$out" "$errors" rubrics "$out/rubrics-index.json" '.[]|[.id,.title]' "/api/v1/courses/$id/rubrics/{id}?include[]=associations" single flat
    recon_get "$out" "$errors" discussions "/api/v1/courses/$id/discussion_topics" collection
    recon_get "$out" "$errors" announcements "/api/v1/courses/$id/discussion_topics?only_announcements=true" collection
    recon_get "$out" "$errors" files "/api/v1/courses/$id/files" collection
    recon_get "$out" "$errors" folders "/api/v1/courses/$id/folders" collection
    recon_get "$out" "$errors" features "/api/v1/courses/$id/features" collection
    recon_get "$out" "$errors" sections "/api/v1/courses/$id/sections" collection
    recon_get "$out" "$errors" grading-standards "/api/v1/courses/$id/grading_standards" collection
    recon_get "$out" "$errors" outcome-groups "/api/v1/courses/$id/outcome_groups" collection
    recon_get "$out" "$errors" outcome-links "/api/v1/courses/$id/outcome_group_links?outcome_style=full&outcome_group_style=full" collection
    recon_get "$out" "$errors" calendar-events "/api/v1/calendar_events?context_codes[]=course_$id&all_events=true" collection

    recon_sanitize "$out"; recon_normalize "$out"; recon_summary "$out"
    printf '\nRecon written to %s\n' "$out" >&2; printf '%s\n' "$out"
}

canvas_recon_diff() {
    local a="$1" b="$2" da db ia ib dir stamp file
    da="$(canvas_recon "$a")" || return 1; db="$(canvas_recon "$b")" || return 1
    ia="$(jq -r .course_id "$da/manifest.json")"; ib="$(jq -r .course_id "$db/manifest.json")"
    dir="$CANVAS_TOOLS_ROOT/comparisons/$ia-vs-$ib"; mkdir -p "$dir"; stamp="$(date -u +'%Y%m%dT%H%M%SZ')"; file="$dir/$stamp.diff"
    if cmp -s "$da/normalized.json" "$db/normalized.json"; then
      printf 'No structural/content differences after normalization.\n' | tee "$file"
    else
      diff -u --label "course-$ia/normalized.json" --label "course-$ib/normalized.json" "$da/normalized.json" "$db/normalized.json" >"$file" || true
      cat "$file"
    fi
    printf 'Comparison saved to %s\n' "$file" >&2
}
