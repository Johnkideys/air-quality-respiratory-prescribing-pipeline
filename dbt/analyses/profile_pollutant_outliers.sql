SELECT
  lower(parameter) AS pollutant,
  APPROX_QUANTILES(value, 1000)[OFFSET(999)] AS p99_9,
  MAX(value) AS max_value
FROM {{ source('raw', 'openaq_measurements') }}
WHERE value >= 0
GROUP BY 1