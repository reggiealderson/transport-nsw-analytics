-- Collapse the many snapshots of each (trip, stop) down to its LAST observation,
-- and classify how much we trust that value. This is the "estimated actual" logic
-- from DATA_FINDINGS §3.6–3.7 / exploration_queries.ESTIMATED_ACTUALS.
--
-- Why the last observation? Stops are dropped from the feed once a train passes
-- them (§3.5), so the final time we saw a (trip, stop) is the closest thing to an
-- actual arrival delay we can get.
--
-- Confidence:
--   * last_seen_ts <  final snapshot of the whole run -> the stop was dropped, i.e.
--     the train really passed it            -> 'estimated_actual'
--   * last_seen_ts == final snapshot        -> the stop was still in the feed when
--     collection stopped, so it's a forecast -> 'prediction'
-- (Every row within one snapshot shares an identical _loaded_at, so equality is exact.)

with base as (
    select
        trip_id,
        service_date,
        stop_id,
        arrival_delay_seconds,
        departure_delay_seconds,
        snapshot_ts
    from {{ ref('stg_rt__trip_updates') }}
    where stop_id is not null          -- drop cancelled-trip base rows (no stop update)
),

ranked as (
    select
        *,
        row_number() over (
            partition by trip_id, stop_id, service_date   -- service_date: distinguishes same trip_id across days
            order by snapshot_ts desc
        ) as rn
    from base
),

collection_end as (
    select max(snapshot_ts) as max_ts from base
)

select
    r.trip_id,
    r.service_date,
    r.stop_id,
    r.arrival_delay_seconds,
    r.departure_delay_seconds,
    r.snapshot_ts as last_seen_ts,
    case
        when r.snapshot_ts = ce.max_ts then 'prediction'
        else 'estimated_actual'
    end as confidence
from ranked r
cross join collection_end ce
where r.rn = 1
