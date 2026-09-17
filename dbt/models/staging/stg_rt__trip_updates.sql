-- Realtime trip updates, one row per (snapshot, trip, stop).
-- Timestamp handling (DATA_FINDINGS §5):
--   * feed_timestamp is a POSIX/UTC integer -> to_timestamp(), then AT TIME ZONE.
--   * _loaded_at is the moment WE polled the feed; every row in a single snapshot
--     shares one _loaded_at value, so it is our snapshot identifier (snapshot_ts).
--   * stop_sequence is always NULL in RT data (§3.1) — do not use it; join on stop_id.
-- Cancelled trips arrive as a base row with a NULL stop_id and no stop update.

with source as (
    select * from {{ source('raw_rt', 'trip_updates') }}
)

select
    entity_id,
    trip_id,
    nullif(stop_id, '')                 as stop_id,
    route_id,
    trip_schedule_relationship,
    stu_schedule_relationship,
    nullif(vehicle_id, '')              as vehicle_id,

    try_cast(arrival_delay as integer)   as arrival_delay_seconds,
    try_cast(departure_delay as integer) as departure_delay_seconds,

    -- the feed's own clock
    to_timestamp(feed_timestamp)                                   as feed_timestamp_utc,
    to_timestamp(feed_timestamp) at time zone 'Australia/Sydney'   as feed_timestamp_syd,

    -- our poll time == the snapshot identifier used for dedup / confidence
    _loaded_at                                                     as snapshot_ts,
    _loaded_at at time zone 'Australia/Sydney'                     as snapshot_ts_syd,

    try_cast(strptime(nullif(start_date, ''), '%Y%m%d') as date)   as service_date
from source
