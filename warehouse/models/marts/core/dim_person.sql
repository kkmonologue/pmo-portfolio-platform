with current_manager_of as (
    select person_id, string_agg(t.team_code, ', ' order by t.team_code) as manages_teams
    from {{ ref('stg_app__team_managers') }} as tm
    join {{ ref('stg_app__teams') }} as t using (team_id)
    where tm.is_current
    group by person_id
)

select
    p.person_id,
    p.display_name,
    p.email,
    p.role,
    p.job_title,
    t.team_code as home_team_code,
    t.office as home_office,
    t.region as home_region,
    p.board_role,
    p.is_board_voter,
    m.manages_teams,
    m.person_id is not null as is_current_manager,
    p.is_departed,
    p.departed_on,
    p.hired_at
from {{ ref('stg_app__people') }} as p
left join {{ ref('stg_app__teams') }} as t on p.home_team_id = t.team_id
left join current_manager_of as m using (person_id)
