select
    submission_id,
    milestone_id,
    submitted_by as submitted_by_id,
    submitted_at,
    form as evidence_form,
    note,
    attachment_name,
    review_status,
    reviewed_by as reviewed_by_id,
    reviewed_at,
    review_comment,
    updated_at
from {{ source('app', 'milestone_submissions') }}
