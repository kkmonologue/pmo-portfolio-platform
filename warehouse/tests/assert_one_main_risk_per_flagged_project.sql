select project_id, count(*) filter (where is_main_risk) as main_risks
from {{ ref('mart_project_risks') }}
group by project_id
having count(*) filter (where is_main_risk) <> 1
