-- One row per non-blank row of the legacy tracker, typed and cleaned.
-- Text dates come in three formats (dd/mm/yyyy on front-office sheets, ISO from real
-- Excel dates, dd.mm.yyyy on middle-office sheets) plus "TBD"; old status labels are
-- mapped through the tracker_status_map seed; rows pasted twice are flagged.
with src as (
    select * from {{ source('tracker', 'tracker_rows') }}
),

typed as (
    select
        snapshot_week,
        -- Monday of the ISO week in the file name
        cast(date_trunc('week', make_date(cast(left(snapshot_week, 4) as integer), 1, 4))
            + to_days((cast(right(snapshot_week, 2) as integer) - 1) * 7) as date) as snapshot_date,
        file_name,
        sheet_name,
        layout,
        regexp_replace(sheet_name, '^HQ - ', '') as sheet_team_name,
        source_row,
        upper(trim(project_ref)) as project_ref,
        trim(project_name) as project_name,
        trim(owner) as owner_typed,
        nullif(trim(status), '') as legacy_status,
        start_raw,
        end_raw,
        try_strptime(start_raw, ['%d/%m/%Y', '%Y-%m-%d', '%d.%m.%Y'])::date as start_date,
        try_strptime(end_raw, ['%d/%m/%Y', '%Y-%m-%d', '%d.%m.%Y'])::date as planned_end,
        coalesce(try_cast(extensions as integer), 0) as extension_count,
        latest_update
    from src
),

mapped as (
    select
        t.*,
        m.mapped_status,
        string_split(m.compatible_statuses, '|') as compatible_statuses,
        row_number() over (
            partition by t.snapshot_week, t.sheet_name, t.project_ref, t.project_name, t.owner_typed,
                t.legacy_status, t.start_raw, t.end_raw, t.extension_count, t.latest_update
            order by t.source_row
        ) > 1 as is_duplicate_row
    from typed as t
    left join {{ ref('tracker_status_map') }} as m on t.legacy_status = m.legacy_status
)

select * from mapped
