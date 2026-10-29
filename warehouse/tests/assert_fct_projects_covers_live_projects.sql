-- Every live project appears exactly once in fct_projects.
select
    (select count(*) from {{ ref('stg_app__projects') }} where not is_deleted) as live_projects,
    (select count(*) from {{ ref('fct_projects') }}) as fact_rows
where live_projects <> fact_rows
