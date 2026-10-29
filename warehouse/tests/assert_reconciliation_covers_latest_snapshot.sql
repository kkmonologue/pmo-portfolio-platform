-- Every non-duplicate row of the latest tracker snapshot appears exactly once in the reconciliation.
with latest as (
    select * from {{ ref('stg_tracker__rows') }}
    where snapshot_week = (select max(snapshot_week) from {{ ref('stg_tracker__rows') }}) and not is_duplicate_row
)

select l.sheet_name, l.source_row, count(r.source_row) as appearances
from latest as l
left join {{ ref('mart_tracker_reconciliation') }} as r
    on r.sheet_name = l.sheet_name and r.source_row = l.source_row
group by all
having count(r.source_row) <> 1
