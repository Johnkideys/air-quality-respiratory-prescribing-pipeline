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

        -- timestamp handling: split into useful derived columns
        datetime                                        as measured_at,
        DATE(datetime)                                  as measured_date,
        EXTRACT(YEAR FROM datetime)                     as measurement_year,
        EXTRACT(MONTH FROM datetime)                    as measurement_month,
        EXTRACT(HOUR FROM datetime)                     as measurement_hour,

        -- measurement
        parameter                                       as pollutant,
        units                                           as unit,
        value                                           as measured_value,

        -- basic data quality flag
        case
            when value < 0 then true
            else false
        end                                             as is_negative_value

    from source

    where datetime is not null  -- drop rows with no timestamp

)

select * from renamed