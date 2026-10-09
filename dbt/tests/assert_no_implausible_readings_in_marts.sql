-- This asserts the filter is applied:
-- no station-month mean should exceed the reading-level threshold, since
-- every contributing reading was below it.

with thresholds as (
    select * from unnest([
        {% for pollutant, threshold in var('pollutant_reading_thresholds').items() %}
        struct('{{ pollutant }}' as pollutant, {{ threshold }} as max_value)
        {%- if not loop.last %},{% endif %}
        {% endfor %}
    ])
)

select
    m.location_id,
    m.pollutant,
    m.month,
    m.avg_value,
    t.max_value
from {{ ref('int_monthly_air_quality') }} m
join thresholds t
  on lower(m.pollutant) = t.pollutant
where m.avg_value > t.max_value