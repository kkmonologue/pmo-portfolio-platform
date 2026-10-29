-- The date the risk rules and "current" figures are evaluated on: the as_of_date var
-- if given, else the last day that has any activity in the data (the simulator's "today").
select coalesce(
    try_cast(nullif('{{ var("as_of_date") }}', '') as date),
    (select max(sent_at)::date from {{ ref('stg_app__emails') }})
) as as_of_date
