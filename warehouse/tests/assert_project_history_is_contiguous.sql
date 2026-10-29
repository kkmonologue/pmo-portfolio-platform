-- SCD2 versions must have exactly one current row per project and no gaps or overlaps.
with ordered as (
    select
        project_id,
        valid_from,
        valid_to,
        is_current,
        lead(valid_from) over (partition by project_id order by version_no) as next_from
    from {{ ref('dim_project_history') }}
)

select project_id, 'gap or overlap' as problem from ordered where valid_to is distinct from next_from
union all
select project_id, 'not exactly one current version' from ordered group by project_id having count(*) filter (where is_current) <> 1
