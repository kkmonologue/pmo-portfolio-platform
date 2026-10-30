-- One row per update: the extracted signals. If an update was processed by both the
-- rules and an LLM, the LLM result wins. When no extraction has run yet the source table
-- does not exist, and this model returns no rows, so dbt build still works.
{% set src = adapter.get_relation(database=target.database, schema='extract', identifier='status_update_signals') %}
{% if src is not none %}
with ranked as (
    select
        *,
        row_number() over (
            partition by update_id
            order by case when extractor like 'llm:%' then 0 else 1 end, extracted_at desc
        ) as preference
    from {{ source('extract', 'status_update_signals') }}
)

select
    update_id,
    extractor,
    extractor like 'llm:%' as is_llm,
    rag as extracted_rag,
    stated_rag,
    blocked as extracted_blocked,
    risk_count,
    max_risk_severity,
    risks_json,
    next_milestone_date as extracted_next_milestone_date,
    next_milestone_date_precision,
    extracted_at
from ranked
where preference = 1
{% else %}
-- placeholder with the same columns (the source() call keeps the lineage edge in the DAG)
select
    null::bigint as update_id, null::varchar as extractor, null::boolean as is_llm, null::varchar as extracted_rag,
    null::varchar as stated_rag, null::boolean as extracted_blocked, null::integer as risk_count,
    null::varchar as max_risk_severity, null::varchar as risks_json, null::date as extracted_next_milestone_date,
    null::varchar as next_milestone_date_precision, null::timestamp as extracted_at
where false
-- depends_on: {{ source('extract', 'status_update_signals') }}
{% endif %}
