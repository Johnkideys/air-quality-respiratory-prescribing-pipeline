with source as (

    select * from {{ source('raw', 'openaq_measurements')}}

),

renamed as (

    select
        -- ids
        location_id,
        sensors_id,

        -- location info
        location                                        as location_name,
        lat                                             as latitude,
        lon                                             as longitude,

        -- timestamp
        datetime                                        as measured_at,
        DATE(datetime)                                  as measured_date,

        -- measurement
        parameter                                       as pollutant,
        units                                           as unit,
        value                                           as measured_value,

        -- data quality flags
        case
            when value < 0 then true
            else false
        end                                             as is_negative_value,

        -- relevance flag for the respiratory air quality use case.
        -- Filter on this in intermediate models rather than dropping rows here,
        -- so the staging layer remains a faithful representation of source data.
        case
            when lower(parameter) in ('pm25', 'pm2.5', 'pm10', 'no2', 'o3', 'so2')
            then true
            else false
        end                                             as is_respiratory_pollutant


    from source

    where datetime is not null  -- drop rows with no timestamp

),

data_quality_flags as (

    select
        *,
        -- the variable pollutant_reading_thresholds is defined in dbt_project.yml and jinja converts this to a dict
        coalesce(
            case
                {% for pollutant, threshold in var('pollutant_reading_thresholds').items() %}
                when lower(pollutant) = '{{ pollutant }}' then measured_value > {{ threshold }}
                {% endfor %}
                else false
            end,
            false
        )                                               as is_implausible_value

    from renamed

)

select * from data_quality_flags