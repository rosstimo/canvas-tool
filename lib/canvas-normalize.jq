def normalize_html:
  if . == null then null
  else
    gsub("/courses/[0-9]+"; "/courses/<COURSE_ID>") |
    gsub("/files/[0-9]+"; "/files/<FILE_ID>") |
    gsub("/assignments/[0-9]+"; "/assignments/<ASSIGNMENT_ID>") |
    gsub("/quizzes/[0-9]+"; "/quizzes/<QUIZ_ID>") |
    gsub("/modules/[0-9]+"; "/modules/<MODULE_ID>")
  end;

def strip_canvas_ids:
  walk(if type == "object" then
    del(.id,.quiz_id,.course_id,.assignment_id,.assessment_question_id,
        .quiz_group_id,.item_id,.entry_id,.context_id,.rubric_id,
        .rubric_association_id)
  else . end);

($groups | map({key:(.id|tostring),value:.name}) | from_entries) as $group_names |
{
  course: {
    default_view: $course.default_view,
    apply_assignment_group_weights: $course.apply_assignment_group_weights,
    grading_standard_present: ($course.grading_standard_id != null),
    course_format: $course.course_format
  },
  settings: ($settings | with_entries(select(.key | endswith("_id") | not))),
  tabs: ($tabs | map({id,label,type,hidden,visibility,position}) | sort_by(.position,.label)),
  modules: ($module_items | map({
    name:.title,
    position:.source_position,
    items:(.items | map({title,type,position,indent,completion_requirement,
      content_details:((.content_details // null)|strip_canvas_ids)}) | sort_by(.position,.title))
  }) | sort_by(.position,.name)),
  assignment_groups: ($groups | map({name,position,group_weight,rules}) | sort_by(.position,.name)),
  assignments: ($assignments | map({
    name,
    description:(.description|normalize_html),
    assignment_group:($group_names[(.assignment_group_id|tostring)] // null),
    points_possible,grading_type,submission_types,published,omit_from_final_grade,
    peer_reviews,automatic_peer_reviews,anonymous_peer_reviews,grade_group_students_individually
  }) | sort_by(.assignment_group,.name)),
  classic_quizzes: ($classic_quizzes | map({
    title,description:(.description|normalize_html),quiz_type,
    assignment_group:($group_names[(.assignment_group_id|tostring)] // null),
    points_possible,time_limit,shuffle_answers,allowed_attempts,scoring_policy,
    one_question_at_a_time,cant_go_back,published,question_count,show_correct_answers
  }) | sort_by(.title)),
  classic_quiz_questions: ($classic_questions | map({title,questions:(.items|map(strip_canvas_ids))}) | sort_by(.title)),
  new_quizzes: ($new_quizzes | map({title,instructions:(.instructions|normalize_html),points_possible,
    grading_type,published,quiz_settings:(.quiz_settings|strip_canvas_ids)}) | sort_by(.title)),
  new_quiz_items: ($new_items | map({title,items:(.items|strip_canvas_ids)}) | sort_by(.title)),
  pages: ($pages | map({title,body:(.body|normalize_html),published,front_page,editing_roles}) | sort_by(.title)),
  rubrics: ($rubrics | map({title,points_possible,free_form_criterion_comments,hide_score_total,
    data:((.data // []) | map({description,long_description,points,criterion_use_range,
      ratings:((.ratings // [])|map({description,long_description,points}))}))}) | sort_by(.title)),
  discussions: ($discussions | map({title,message:(.message|normalize_html),discussion_type,published,pinned,
    require_initial_post,allow_rating,only_graders_can_rate,sort_by_rating,anonymous_state}) | sort_by(.title)),
  announcements: ($announcements | map({title,message:(.message|normalize_html),published}) | sort_by(.title)),
  files: ($files | map({display_name,filename,size,content_type:."content-type",hidden,locked,visibility_level}) | sort_by(.display_name)),
  folders: ($folders | map({name,full_name,position,locked}) | sort_by(.full_name)),
  features: ($features | map({feature,display_name,applies_to,state:.feature_flag.state}) | sort_by(.feature)),
  grading_standards: ($grading_standards | map({title,points_based,scaling_factor,grading_scheme}) | sort_by(.title)),
  outcomes: ($outcome_links | map(strip_canvas_ids) | sort_by((.outcome.title // ""),(.outcome.display_name // ""))),
  calendar_events: ($calendar_events | map({title,description:(.description|normalize_html),location_name,
    location_address,all_day,workflow_state,important_dates,blackout_date}) | sort_by(.title))
}
