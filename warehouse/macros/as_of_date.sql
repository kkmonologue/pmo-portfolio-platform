{#- The evaluation date as a SQL expression: the as_of_date var if set, else the latest day in the data. -#}
{% macro as_of_date() -%}
    (select as_of_date from {{ ref('int_as_of_date') }})
{%- endmacro %}
