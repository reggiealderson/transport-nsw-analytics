# Data findings — TfNSW Sydney Trains GTFS

This document records everything learned from hands-on exploration of the TfNSW GTFS static and realtime datasets. It is intended as context for Claude Code when building the dbt project. Every claim below was verified empirically unless stated otherwise.

---

## 1. API endpoints and authentication

| Feed | URL | Format |
|---|---|---|
| Static GTFS bundle | `https://api.transport.nsw.gov.au/v1/gtfs/schedule/sydneytrains` | ZIP of CSV files |
| Realtime trip updates | `https://api.transport.nsw.gov.au/v2/gtfs/realtime/sydneytrains` | Protobuf (GTFS-R) |

- The static endpoint is **v1**. The realtime endpoint is **v2**. Do not use v2 for the static bundle — it returns 404.
- Authentication: pass the API key as `Authorization: apikey <key>` in the request header.
- The API key is stored in the environment variable `TFNSW_API_KEY`. Never commit it.
- The static bundle updates daily at approximately 01:30 AEST.
- The realtime feed updates every 10 seconds on the TfNSW side.

---

## 2. Static GTFS tables

### 2.1 Table inventory and row counts (observed 2026-09-17)

| Table | Rows | Role |
|---|---|---|
| `agency` | 2 | Lookup — operators |
| `routes` | 137 | Lookup — train lines |
| `calendar` | 121 | Reference — service day patterns |
| `stops` | 1,214 | Reference — stations and platforms |
| `trips` | 65,947 | Fact-like — one row per train journey |
| `stop_times` | 1,209,051 | Fact — scheduled arrival/departure per trip per stop |
| `shapes` | 96,691 | Reference — GPS route geometry (not needed for delay analysis) |
| `occupancies` | 518,137 | TfNSW extension — not standard GTFS, ignore for now |
| `vehicle_boardings` | 15,631 | TfNSW extension — ignore for now |
| `vehicle_couplings` | 183 | TfNSW extension — ignore for now |
| `vehicle_categories` | 46 | TfNSW extension — ignore for now |

### 2.2 `agency`

Two operators share the bundle:
- **Sydney Trains** — suburban network.
- **NSW TrainLink** — intercity services (Blue Mountains, Central Coast, South Coast, Hunter).

Both use the same stations and tracks. Filter to Sydney Trains alone if scope needs to be reduced.

### 2.3 `routes`

A route is a **line on the network map**, not a single train. Example: "T1 North Shore Line."

- `route_short_name` is the line code (T1, T2, T4, etc.).
- `route_type` = `2` for rail. Other values may appear for coach replacements.
- A single route can have thousands of trips because the route runs many services per day across many days in the timetable period.

### 2.4 `calendar`

Defines which days each service pattern runs.

- Columns: `service_id`, `monday` through `sunday` (1 = runs, 0 = does not run), `start_date`, `end_date`.
- The date range defines the **timetable validity period**, not the realtime window. Observed: 20260917 to 20261016.
- A `calendar_dates` table may also exist for exceptions (public holidays, special events). Check for it.
- Trips link to this table through `service_id`.

### 2.5 `stops` — parent/child structure

This table has a two-level hierarchy:

- **Parent station** = the station itself (e.g. "Central Station"). Has `location_type = 1` or empty `parent_station`.
- **Child stop** = a specific platform (e.g. "Central Station Platform 17"). Has `parent_station` pointing to the parent's `stop_id`.

**Critical finding**: both the static `stop_times` table and the realtime feed use **platform-level** (child) `stop_id` values. The join between them works at this level. But for reporting, always join through to the **parent station** for readable names. Example:

- `stop_id` `2000337` → "Central Station Platform 17" → parent `200060` → "Central Station"
- `stop_id` `2000396` → "Town Hall Station Platform 6" → parent `200070` → "Town Hall Station"

### 2.6 `stop_times`

The largest and most important table. One row = "trip X arrives at stop Y at time Z."

- `stop_sequence` is the order of stops within a trip. Starts at 0 (observed), not 1.
- `arrival_time` and `departure_time` are **strings**, not time types. They can exceed 24:00:00 — e.g. `25:10:00` means 01:10 the next calendar day, but belongs to the previous service day. Always load as text and convert to seconds-past-midnight for arithmetic.
- `pickup_type` and `drop_off_type`: 0 = passengers can board/alight.
- The explore script loads all columns as text (dtype=str) to avoid type-detection problems with the time format.

### 2.7 `trips`

One row per train journey.

- `trip_id` is the primary key and the main join key to realtime data.
- `route_id` links to `routes`.
- `service_id` links to `calendar`.
- `direction_id` is 0 or 1 (outbound/inbound). The GTFS spec does not define which is which — determine from data.
- `trip_headsign` is the destination shown on the front of the train.
- `shape_id` links to `shapes` (GPS path — not needed for delay analysis).

### 2.8 Static data change detection

The static bundle has **no version number and no change log**. TfNSW publishes a new bundle daily. If a platform is added, a route renamed, or a timetable altered, the change appears silently in the next bundle. In a production pipeline you would detect changes by downloading daily and comparing. For this project, download once and use it for the duration of data collection. Document this as a known limitation.

---

## 3. Realtime feed behaviour

These findings were verified by collecting 20 snapshots at 30-second intervals during the evening peak on 2026-09-17.

### 3.1 What a snapshot contains

Each API call returns the state of **every currently active trip** on the network at that instant. A trip is "active" from shortly before its first departure until shortly after it reaches its final stop. Completed trips are removed from the feed. A train that ran at 6am will not appear in a snapshot taken at 2pm.

Each trip's entry contains a list of `stop_time_update` records — one per stop on the trip's route. Each record has:

- `stop_id` — matches the platform-level stop_id in the static data.
- `stop_sequence` — **always NULL** in the observed Sydney Trains data. Do not rely on it.
- `arrival_delay` — delay in **seconds** relative to the scheduled arrival time. Positive = late, negative = early.
- `arrival_time` — predicted arrival as a POSIX/Unix timestamp (UTC). May be NULL.
- `departure_delay` — same concept for departure.
- `schedule_relationship` at the trip level — `SCHEDULED`, `ADDED`, `CANCELED`.
- `schedule_relationship` at the stop level — `SCHEDULED`, `SKIPPED`.

### 3.2 The join key is `trip_id` + `stop_id`

Do **not** join on `stop_sequence`. It is NULL in the realtime data. Use `trip_id` + `stop_id` to match realtime rows to the static `stop_times` table. Verified: 0 orphans out of 448 realtime trips when joining this way.

### 3.3 Delay values are predictions, never labelled actuals

There is no field that distinguishes "this is a measured actual" from "this is a forecast." Every `arrival_delay` value is technically a prediction. The feed does not update a value to an "actual" after the train passes a stop.

### 3.4 Delay values fluctuate and do not stabilise

Observed for St James Station (scheduled 18:26:18): across 20 snapshots covering the 10 minutes before expected arrival, `arrival_delay` ranged from 492 to 568 seconds (8.2 to 9.5 minutes). Values did not converge. Fluctuations of up to 70 seconds were observed even in the final snapshots.

### 3.5 Stops are dropped after the train passes

This is the most important behavioural finding. When a train passes a stop, that stop is **removed** from the trip's `stop_time_update` list in subsequent snapshots. Observed:

- Town Hall (scheduled 18:17:18): present in 9 snapshots, then gone.
- Wynyard (scheduled 18:20:00): present in 13 snapshots, then gone.
- St James (scheduled 18:26:18): present in all 20 snapshots — train had not yet arrived.

Stops earlier in the trip disappear first. Stops later in the trip persist until the train reaches them.

### 3.6 Defining "estimated actual delay"

Because stops are dropped after the train passes, the **last snapshot that includes a stop for a given trip** contains the closest-to-actual delay value. This is the project's definition of "estimated actual delay."

Implementation: for each (trip_id, stop_id) pair, take the row with the maximum `snapshot_ts`. This is a `ROW_NUMBER() OVER (PARTITION BY trip_id, stop_id ORDER BY snapshot_ts DESC) = 1` pattern.

### 3.7 Distinguishing estimated actuals from predictions

If the `last_seen` timestamp for a stop equals the final snapshot timestamp of the entire collection run, the train had **not yet passed** that stop when collection ended. The value is still a prediction.

Implementation: compare each stop's `last_seen` to the global `max(snapshot_ts)`.

- `last_seen < max(snapshot_ts)` → stop was dropped → **estimated actual**
- `last_seen = max(snapshot_ts)` → stop was still in the feed → **prediction only**

In the dbt model, expose this as a `confidence` column with values `estimated_actual` or `prediction`. Add a quality test that warns if more than a threshold percentage of stops in the final mart are marked `prediction`.

### 3.8 Trips that span the collection boundary

Trips that were still running when the poller stopped will have their later stops marked as `prediction`. Trips that started after the poller stopped are missing entirely. For a 24-hour collection run, only the last ~1 hour of services will be affected. Document this as a known limitation.

---

## 4. Polling design

- **Recommended interval**: every 60 seconds.
- **Rationale**: the shortest gaps between consecutive stops on a trip are approximately 2 minutes. Polling every 60 seconds guarantees every stop is observed in at least one snapshot before it is dropped.
- **Slower polling (e.g. 5 minutes)**: still works for coarse analysis ("which routes are worst") but risks missing stops entirely if two consecutive stops are close together. Also increases the gap between the last observation and actual arrival, adding up to 5 minutes of noise.
- **Faster polling (e.g. 10 seconds)**: matches the feed refresh rate but generates large volumes of near-duplicate data for minimal accuracy gain.
- **Resilience**: if the poller crashes or pauses, trips during the gap are lost. The poller should log gaps and the dbt model should account for them.

---

## 5. Data type and format gotchas

| Issue | Detail | How to handle |
|---|---|---|
| GTFS arrival/departure times | Strings like `25:10:00` that exceed 24h | Load as text. Convert to seconds-past-midnight for arithmetic. |
| `stop_sequence` in realtime | Always NULL for Sydney Trains | Join on `trip_id` + `stop_id` instead. |
| `feed_timestamp` | POSIX integer, UTC | Convert with `to_timestamp()` and apply `AT TIME ZONE 'Australia/Sydney'`. |
| `start_date` in realtime | String like `20260917` | Parse as date for joining to calendar. |
| All static columns | Loaded as text (dtype=str) to avoid type-detection issues | Cast explicitly in staging models. |
| `parent_station` on parent stops | Empty string, not NULL | Filter with `parent_station IS NOT NULL AND parent_station != ''`. |

---

## 6. Verified query patterns

### Join realtime to static schedule (the core join)

```sql
SELECT
    CAST(st.stop_sequence AS INTEGER) AS seq,
    parent.stop_name AS station,
    st.arrival_time AS scheduled,
    rt.arrival_delay AS delay_seconds
FROM raw_rt.trip_updates rt
JOIN raw_gtfs.stop_times st
    ON rt.trip_id = st.trip_id
    AND rt.stop_id = st.stop_id
JOIN raw_gtfs.stops platform ON st.stop_id = platform.stop_id
JOIN raw_gtfs.stops parent ON platform.parent_station = parent.stop_id
ORDER BY CAST(st.stop_sequence AS INTEGER)
```

### Deduplicate to last observation per stop (estimated actual)

```sql
WITH last_snapshot AS (
    SELECT
        trip_id,
        stop_id,
        arrival_delay,
        snapshot_ts,
        ROW_NUMBER() OVER (
            PARTITION BY trip_id, stop_id
            ORDER BY snapshot_ts DESC
        ) AS rn
    FROM raw_rt.poller_test
),
collection_end AS (
    SELECT max(snapshot_ts) AS max_ts
    FROM raw_rt.poller_test
)
SELECT
    ls.trip_id,
    ls.stop_id,
    ls.arrival_delay AS last_delay_seconds,
    ls.snapshot_ts AS last_seen_ts,
    CASE
        WHEN ls.snapshot_ts = ce.max_ts THEN 'prediction'
        ELSE 'estimated_actual'
    END AS confidence
FROM last_snapshot ls
CROSS JOIN collection_end ce
WHERE ls.rn = 1
```

### Orphan rate check (referential integrity)

```sql
SELECT
    count(DISTINCT r.trip_id) AS rt_trips,
    count(DISTINCT r.trip_id) FILTER (WHERE t.trip_id IS NULL) AS orphans
FROM raw_rt.trip_updates r
LEFT JOIN raw_gtfs.trips t USING (trip_id)
```

---

## 7. Questions the project can answer

- Which routes have the worst on-time performance?
- Which stations see the most delays?
- Do delays accumulate as a trip progresses (does the train lose time)?
- Is morning peak worse than evening peak?
- How does weekday performance compare to weekend?

All require a full day of polled data (24 hours) to answer properly.

---

## 8. Classification and sensitivity

All data in these feeds is **public**. No personal information is present. Tag all tables as `classification: public` in dbt meta. Note in the governance README that you assessed sensitivity and found none.

---

## 9. Known limitations to document

1. **No actual arrival times** — delays are always estimates based on the last prediction before a stop is dropped from the feed.
2. **Prediction fluctuation** — delay values can vary by up to 70 seconds in the minutes before arrival.
3. **Polling gaps** — any period where the poller is not running results in lost trip data for that window.
4. **Collection boundary** — trips running when the poller stops have their later stops marked as predictions, not estimated actuals.
5. **Static bundle versioning** — no change detection mechanism. A single bundle is assumed valid for the collection period.
6. **stop_sequence** — NULL in realtime data. Not usable as a join key.
