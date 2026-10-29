select
    milestone_id,
    project_id,
    seq as milestone_seq,
    name as milestone_name,
    evidence_forms,
    original_due_date,
    due_date,
    due_date - original_due_date as days_moved,
    status as milestone_status,
    accepted_on,
    created_at,
    updated_at
from {{ source('app', 'milestones') }}
