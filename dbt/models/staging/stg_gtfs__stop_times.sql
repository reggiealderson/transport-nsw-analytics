-- Scheduled arrival/departure per trip per stop.
-- Gotcha (DATA_FINDINGS §2.6): arrival_time/departure_time are strings that can
-- exceed 24:00:00 (e.g. '25:10:00' = 01:10 the next calendar day, but belonging to
-- the previous service day). We DO NOT try to coerce them to a TIME type. We keep
-- the original text and additionally expose seconds-past-service-day-midnight for
-- safe arithmetic.

with source as (
    select * from {{ source('raw_gtfs', 'stop_times') }}
)

select
    trip_id,
    stop_id,
    try_cast(nullif(stop_sequence, '') as integer) as stop_sequence,

    -- original text, preserved verbatim (may be >= 24:00:00)
    nullif(arrival_time, '')   as arrival_time_text,
    nullif(departure_time, '') as departure_time_text,

    -- seconds past the service-day start (handles the 24h+ overflow correctly)
    case when nullif(arrival_time, '') is not null then
        cast(split_part(arrival_time, ':', 1) as integer) * 3600
      + cast(split_part(arrival_time, ':', 2) as integer) * 60
      + cast(split_part(arrival_time, ':', 3) as integer)
    end as arrival_seconds_past_midnight,

    -- same for departure (used to derive each trip's scheduled journey start at its origin)
    case when nullif(departure_time, '') is not null then
        cast(split_part(departure_time, ':', 1) as integer) * 3600
      + cast(split_part(departure_time, ':', 2) as integer) * 60
      + cast(split_part(departure_time, ':', 3) as integer)
    end as departure_seconds_past_midnight,

    try_cast(nullif(pickup_type, '')   as integer) as pickup_type,
    try_cast(nullif(drop_off_type, '') as integer) as drop_off_type
from source
