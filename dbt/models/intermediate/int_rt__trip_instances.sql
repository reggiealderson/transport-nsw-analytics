-- One row per real journey INSTANCE, identified by the composite key (trip_id, service_date)
-- because a trip_id is reused every day it runs (see docs). This model assembles the three
-- distinct "start" timestamps for each instance:
--   * scheduled_start   — from the static timetable (origin stop's scheduled departure),
--                         anchored to this instance's service_date.
--   * actual_start      — scheduled_start + the estimated-actual departure delay at the origin
--                         ("when it really left").
--   * feed_first_seen   — the first snapshot the trip appeared in (a COLLECTION artifact, used
--                         only to measure how far ahead of departure trips enter the feed).
-- All timestamps are Sydney wall-clock.

with rt as (
    select * from {{ ref('stg_rt__trip_updates') }}
),

-- one row per observed instance, with feed-presence window
instances as (
    select
        trip_id,
        service_date,
        max(route_id)            as route_id,
        min(snapshot_ts_syd)     as feed_first_seen,
        max(snapshot_ts_syd)     as feed_last_seen,
        count(distinct snapshot_ts) as n_snapshots
    from rt
    group by 1, 2
),

-- each trip's ORIGIN stop (min stop_sequence) and its scheduled departure, from the static schedule
origin as (
    select
        trip_id,
        stop_id                          as origin_stop_id,
        departure_seconds_past_midnight  as origin_dep_seconds
    from {{ ref('stg_gtfs__stop_times') }}
    qualify row_number() over (partition by trip_id order by stop_sequence) = 1
),

-- the estimated-actual departure delay observed at the origin, per instance
origin_delay as (
    select trip_id, service_date, stop_id, departure_delay_seconds
    from {{ ref('int_rt__latest_update') }}
)

select
    i.trip_id,
    i.service_date,
    i.route_id,
    o.origin_stop_id,

    -- scheduled journey start = service-day midnight + scheduled origin-departure seconds
    (i.service_date::timestamp + to_seconds(o.origin_dep_seconds))                       as scheduled_start,

    od.departure_delay_seconds                                                           as origin_departure_delay_seconds,

    -- actual journey start = scheduled start shifted by the observed origin departure delay
    (i.service_date::timestamp + to_seconds(o.origin_dep_seconds)
        + to_seconds(od.departure_delay_seconds))                                        as actual_start,

    i.feed_first_seen,
    i.feed_last_seen,
    i.n_snapshots,

    -- feed lead time: how many seconds before scheduled departure did the trip appear?
    -- (positive = appeared before departure). This VALIDATES the "first-seen ~ departure" claim.
    date_diff('second', i.feed_first_seen,
              (i.service_date::timestamp + to_seconds(o.origin_dep_seconds)))            as feed_lead_seconds
from instances i
left join origin o
    on i.trip_id = o.trip_id
left join origin_delay od
    on i.trip_id = od.trip_id
   and i.service_date = od.service_date
   and od.stop_id = o.origin_stop_id
