-- One row per extracted status update: what the text says (RAG, risks, blocker, next date)
-- next to the facts the system knows (project, meeting, typed colour vs judged colour).
select
    u.update_id,
    u.project_id,
    u.project_code,
    u.team_code,
    u.office,
    u.posted_at,
    u.meeting_date,
    s.extractor,
    s.is_llm,
    s.extracted_rag,
    s.stated_rag,
    s.stated_rag is not null and s.stated_rag <> s.extracted_rag as stated_differs_from_content,
    s.extracted_blocked,
    s.risk_count,
    s.max_risk_severity,
    s.risks_json,
    s.extracted_next_milestone_date,
    s.next_milestone_date_precision,
    row_number() over (partition by u.project_id order by u.posted_at desc) = 1 as is_latest_for_project
from {{ ref('fct_status_updates') }} as u
join {{ ref('stg_extract__status_update_signals') }} as s using (update_id)
