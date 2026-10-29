{#- Fails when a combination of columns is not unique (a dependency-free version of dbt_utils.unique_combination_of_columns). -#}
{% test unique_combination(model, columns) %}
select {{ columns | join(', ') }}, count(*) as n
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}
