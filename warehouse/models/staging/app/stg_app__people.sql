select
    person_id,
    display_name,
    lower(email) as email,
    home_team_id,
    role,
    job_title,
    board_role,
    board_role in ('steering', 'execution') as is_board_voter,
    status as employment_status,
    departed_on,
    status = 'departed' as is_departed,
    created_at as hired_at,
    updated_at
from {{ source('app', 'people') }}
