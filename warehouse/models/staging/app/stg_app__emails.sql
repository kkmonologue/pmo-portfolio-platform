select
    email_id,
    rule as email_rule,
    rule like 'R%' as is_reminder,
    project_id,
    to_ids,
    cc_ids,
    len(string_split(to_ids, ',')) as to_count,
    subject,
    sent_at,
    updated_at
from {{ source('app', 'emails') }}
