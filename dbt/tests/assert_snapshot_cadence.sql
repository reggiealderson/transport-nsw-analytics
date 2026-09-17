-- DAMA-DMBOK dimension: TIMELINESS.
-- The poller is meant to snapshot every 60s. This test surfaces any gap between
-- consecutive snapshots longer than 150s (2.5x the interval) — i.e. a period where
-- the poller stalled or was asleep and trip data was lost (DATA_FINDINGS §4).
-- Warn-only: gaps are a documented, accepted limitation, not a build-breaking defect.
-- A "clean" run returns zero rows.
{{ config(severity='warn') }}

with snapshots as (
    select distinct snapshot_ts
    from {{ ref('stg_rt__trip_updates') }}
),

gaps as (
    select
        snapshot_ts,
        lag(snapshot_ts) over (order by snapshot_ts) as prev_snapshot_ts,
        date_diff(
            'second',
            lag(snapshot_ts) over (order by snapshot_ts),
            snapshot_ts
        ) as gap_seconds
    from snapshots
)

select *
from gaps
where gap_seconds > 150
order by gap_seconds desc
