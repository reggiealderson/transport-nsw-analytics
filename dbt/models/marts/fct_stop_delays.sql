-- One row per (trip, stop): the estimated-actual (or predicted) arrival delay,
-- joined through to readable station + line names. This is the analysis-ready fact
-- table behind every question in DATA_FINDINGS §7.
--
-- Join rules (DATA_FINDINGS §3.2, §2.5):
--   * realtime -> static on trip_id + stop_id (NEVER stop_sequence, it's NULL in RT).
--   * platform stop -> parent station for a readable name (fall back to the platform
--     name if a stop has no parent).

with latest as (
    select * from {{ ref('int_rt__latest_update') }}
),
stop_times as (
    select * from {{ ref('stg_gtfs__stop_times') }}
),
stops as (
    select * from {{ ref('stg_gtfs__stops') }}
),
trips as (
    select * from {{ ref('stg_gtfs__trips') }}
),
routes as (
    select * from {{ ref('stg_gtfs__routes') }}
)

select
    -- surrogate key for the uniqueness test (one estimate per trip+stop+service_date)
    latest.trip_id || '-' || latest.stop_id || '-' || latest.service_date  as stop_delay_key,

    latest.trip_id,
    latest.service_date,
    latest.stop_id,
    coalesce(parent.stop_name, platform.stop_name)             as station,
    routes.route_short_name,
    trips.trip_headsign,
    trips.direction_id,

    stop_times.stop_sequence                                   as scheduled_stop_sequence,
    stop_times.arrival_time_text                               as scheduled_arrival,

    latest.arrival_delay_seconds,
    round(latest.arrival_delay_seconds / 60.0, 1)              as arrival_delay_minutes,

    latest.last_seen_ts,
    latest.confidence
from latest
join stop_times
    on latest.trip_id = stop_times.trip_id
   and latest.stop_id = stop_times.stop_id
join stops platform
    on stop_times.stop_id = platform.stop_id
left join stops parent
    on platform.parent_station = parent.stop_id
join trips
    on latest.trip_id = trips.trip_id
join routes
    on trips.route_id = routes.route_id
