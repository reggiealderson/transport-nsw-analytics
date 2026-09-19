-- One row per journey INSTANCE (trip_id + service_date): scheduled vs actual departure and the
-- feed-appearance lead time. This is the trip-level companion to the stop-level fct_stop_delays.
-- Contains every service day collected; scope to a single day (e.g. service_date = the Friday)
-- for the article's analysis — the model itself is left day-agnostic so multi-day / rolling
-- analysis works without changes.

with ti as (
    select * from {{ ref('int_rt__trip_instances') }}
),
trips as (
    select * from {{ ref('stg_gtfs__trips') }}
),
routes as (
    select * from {{ ref('stg_gtfs__routes') }}
)

select
    ti.trip_id || '-' || ti.service_date            as trip_instance_key,
    ti.trip_id,
    ti.service_date,
    routes.route_short_name,
    trips.trip_headsign,
    trips.direction_id,

    ti.scheduled_start,
    ti.actual_start,
    ti.origin_departure_delay_seconds,
    round(ti.origin_departure_delay_seconds / 60.0, 1) as origin_departure_delay_minutes,

    ti.feed_first_seen,
    ti.feed_lead_seconds,
    round(ti.feed_lead_seconds / 60.0, 1)              as feed_lead_minutes,
    ti.n_snapshots
from ti
left join trips  on ti.trip_id = trips.trip_id
left join routes on trips.route_id = routes.route_id
