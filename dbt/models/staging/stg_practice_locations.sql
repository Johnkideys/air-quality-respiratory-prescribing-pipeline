with source as (

    select * from {{ source('raw', 'practice_locations') }}

),

renamed as (

    select
        -- ids
        practice_code,
        practice_name,

        -- setting type (integer code) (setting=4 is gp practice)
        setting,

        -- geography
        lat                 as latitude,
        lon                 as longitude

    from source

    where practice_code is not null

)

select * from renamed