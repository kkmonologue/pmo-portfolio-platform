-- Calendar with ISO weeks and the bi-weekly meeting pattern (Thursdays: front office in
-- even ISO weeks, middle office in odd ISO weeks).
with days as (
    select cast(unnest(generate_series(date '2024-01-01', date '2027-12-31', interval 1 day)) as date) as date_day
)

select
    date_day,
    year(date_day) as calendar_year,
    quarter(date_day) as calendar_quarter,
    month(date_day) as calendar_month,
    monthname(date_day) as month_name,
    isoyear(date_day) as iso_year,
    week(date_day) as iso_week,
    isoyear(date_day) || '-W' || lpad(week(date_day)::varchar, 2, '0') as iso_year_week,
    isodow(date_day) as iso_weekday,
    isodow(date_day) >= 6 as is_weekend,
    case when isodow(date_day) = 4 then case when week(date_day) % 2 = 0 then 'front' else 'middle' end end as meeting_track
from days
