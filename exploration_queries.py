"""
Verified exploration queries — TfNSW Sydney Trains GTFS.

These queries were tested on 2026-09-17 and confirmed to return correct results.
Use them as reference when building dbt staging and intermediate models.
Run in a Jupyter notebook with:
    import duckdb
    con = duckdb.connect("gtfs.duckdb")
"""

# =============================================================================
# STATIC DATA EXPLORATION
# =============================================================================

# Table inventory and row counts
TABLE_COUNTS = """
    SELECT table_schema, table_name, estimated_size
    FROM duckdb_tables()
    ORDER BY estimated_size DESC
"""

# Two agencies: Sydney Trains and NSW TrainLink
AGENCIES = """
    SELECT * FROM raw_gtfs.agency
"""

# Route types — expect route_type=2 for rail
ROUTE_TYPES = """
    SELECT route_type, count(*) AS routes
    FROM raw_gtfs.routes
    GROUP BY 1
"""

# Trips per route — shows why one route has thousands of trips
TRIPS_PER_ROUTE = """
    SELECT
        r.route_short_name,
        count(DISTINCT t.trip_id) AS total_trips,
        count(DISTINCT c.service_id) AS service_patterns,
        round(count(DISTINCT t.trip_id) / count(DISTINCT c.service_id)) AS approx_trips_per_pattern
    FROM raw_gtfs.trips t
    JOIN raw_gtfs.routes r USING (route_id)
    JOIN raw_gtfs.calendar c USING (service_id)
    GROUP BY 1
    ORDER BY 2 DESC
    LIMIT 10
"""

# Calendar validity period — the timetable date range, NOT the realtime window
CALENDAR_RANGE = """
    SELECT min(start_date) AS earliest, max(end_date) AS latest
    FROM raw_gtfs.calendar
"""

# Service day patterns — weekday-only, weekend-only, daily etc
SERVICE_PATTERNS = """
    SELECT
        monday, tuesday, wednesday, thursday, friday, saturday, sunday,
        count(*) AS service_patterns
    FROM raw_gtfs.calendar
    GROUP BY 1,2,3,4,5,6,7
    ORDER BY 8 DESC
"""

# Stops parent/child structure — stations with most platforms
STATIONS_BY_PLATFORMS = """
    SELECT
        p.stop_name AS station,
        count(*) AS platforms
    FROM raw_gtfs.stops c
    JOIN raw_gtfs.stops p ON c.parent_station = p.stop_id
    WHERE c.parent_station IS NOT NULL AND c.parent_station != ''
    GROUP BY 1
    ORDER BY 2 DESC
    LIMIT 10
"""

# GTFS times past midnight — the service-day gotcha
TIMES_PAST_MIDNIGHT = """
    SELECT arrival_time, count(*) AS n
    FROM raw_gtfs.stop_times
    WHERE arrival_time >= '24:00:00'
    GROUP BY 1
    ORDER BY 1
    LIMIT 10
"""

# Full journey for a single trip — every stop in order
# Replace TRIP_ID with an actual trip_id value
SINGLE_TRIP_JOURNEY = """
    SELECT
        CAST(st.stop_sequence AS INTEGER) AS seq,
        parent.stop_name AS station,
        st.arrival_time AS scheduled,
        st.departure_time
    FROM raw_gtfs.stop_times st
    JOIN raw_gtfs.stops platform ON st.stop_id = platform.stop_id
    JOIN raw_gtfs.stops parent ON platform.parent_station = parent.stop_id
    WHERE st.trip_id = '{trip_id}'
    ORDER BY CAST(st.stop_sequence AS INTEGER)
"""

# Gap between consecutive stops on a trip — used to determine safe polling interval
# Smallest gap determines the minimum polling frequency to avoid missing stops
STOP_GAPS = """
    SELECT
        CAST(st.stop_sequence AS INTEGER) AS seq,
        parent.stop_name AS station,
        st.arrival_time AS this_stop,
        LEAD(st.arrival_time) OVER (ORDER BY CAST(st.stop_sequence AS INTEGER)) AS next_stop
    FROM raw_gtfs.stop_times st
    JOIN raw_gtfs.stops platform ON st.stop_id = platform.stop_id
    JOIN raw_gtfs.stops parent ON platform.parent_station = parent.stop_id
    WHERE st.trip_id = '{trip_id}'
    ORDER BY CAST(st.stop_sequence AS INTEGER)
"""


# =============================================================================
# REALTIME DATA EXPLORATION
# =============================================================================

# Feed timestamp as readable Sydney time
FEED_TIMESTAMP = """
    SELECT
        feed_timestamp,
        to_timestamp(feed_timestamp) AT TIME ZONE 'Australia/Sydney' AS feed_time_syd
    FROM raw_rt.trip_updates
    LIMIT 1
"""

# Realtime schedule relationships — expect SCHEDULED, possibly ADDED or CANCELED
RT_SCHEDULE_RELATIONSHIPS = """
    SELECT trip_schedule_relationship, count(DISTINCT trip_id) AS trips
    FROM raw_rt.trip_updates
    GROUP BY 1
"""

# Orphan rate — realtime trips that don't match the static schedule
# Zero orphans = the static bundle and realtime feed are in sync
ORPHAN_RATE = """
    SELECT
        count(DISTINCT r.trip_id) AS rt_trips,
        count(DISTINCT r.trip_id) FILTER (WHERE t.trip_id IS NULL) AS orphans
    FROM raw_rt.trip_updates r
    LEFT JOIN raw_gtfs.trips t USING (trip_id)
"""

# Delay distribution in minutes — from a single snapshot
DELAY_DISTRIBUTION = """
    SELECT
        round(arrival_delay / 60.0) AS delay_minutes,
        count(*) AS count
    FROM raw_rt.trip_updates
    WHERE arrival_delay IS NOT NULL
    GROUP BY 1
    ORDER BY 1
"""

# Verify stop_sequence is NULL in realtime data
RT_STOP_SEQUENCE_CHECK = """
    SELECT
        count(*) AS total_rows,
        count(stop_sequence) AS has_stop_sequence,
        count(*) - count(stop_sequence) AS missing_stop_sequence
    FROM raw_rt.trip_updates
"""


# =============================================================================
# CORE JOIN — realtime to static schedule
# =============================================================================

# Join key is trip_id + stop_id (NOT stop_sequence — it is NULL in RT data)
# Joins through to parent station for readable names
CORE_JOIN = """
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
    WHERE rt.trip_id = '{trip_id}'
    ORDER BY CAST(st.stop_sequence AS INTEGER)
"""


# =============================================================================
# POLLED DATA ANALYSIS — requires raw_rt.poller_test table
# =============================================================================

# Find trips with many snapshots — good candidates for analysis
WELL_OBSERVED_TRIPS = """
    SELECT trip_id, count(DISTINCT snapshot_ts) AS snapshots, count(*) AS rows
    FROM raw_rt.poller_test
    GROUP BY trip_id
    HAVING count(DISTINCT snapshot_ts) > 10
    ORDER BY snapshots DESC
    LIMIT 10
"""

# Watch one stop's delay change across snapshots
# This is the query that proved delay values fluctuate and don't stabilise
DELAY_OVER_TIME_ONE_STOP = """
    SELECT
        to_timestamp(p.snapshot_ts) AT TIME ZONE 'Australia/Sydney' AS snapshot_time,
        parent.stop_name AS station,
        st.arrival_time AS scheduled,
        p.arrival_delay AS delay_seconds
    FROM raw_rt.poller_test p
    JOIN raw_gtfs.stop_times st
        ON p.trip_id = st.trip_id AND p.stop_id = st.stop_id
    JOIN raw_gtfs.stops platform ON p.stop_id = platform.stop_id
    JOIN raw_gtfs.stops parent ON platform.parent_station = parent.stop_id
    WHERE p.trip_id = '{trip_id}'
      AND parent.stop_name = '{station_name}'
    ORDER BY snapshot_time
"""

# Deduplicate to last observation per stop — the "estimated actual" pattern
# This is the core logic for the int_rt_latest_update dbt model
ESTIMATED_ACTUALS = """
    WITH last_snapshot AS (
        SELECT
            p.trip_id,
            p.stop_id,
            p.arrival_delay,
            p.snapshot_ts,
            ROW_NUMBER() OVER (
                PARTITION BY p.trip_id, p.stop_id
                ORDER BY p.snapshot_ts DESC
            ) AS rn
        FROM raw_rt.poller_test p
    ),
    collection_end AS (
        SELECT max(snapshot_ts) AS max_ts
        FROM raw_rt.poller_test
    )
    SELECT
        CAST(st.stop_sequence AS INTEGER) AS seq,
        parent.stop_name AS station,
        st.arrival_time AS scheduled,
        ls.arrival_delay AS last_delay_seconds,
        to_timestamp(ls.snapshot_ts) AT TIME ZONE 'Australia/Sydney' AS last_seen,
        CASE
            WHEN ls.snapshot_ts = ce.max_ts THEN 'prediction'
            ELSE 'estimated_actual'
        END AS confidence
    FROM last_snapshot ls
    CROSS JOIN collection_end ce
    JOIN raw_gtfs.stop_times st
        ON ls.trip_id = st.trip_id AND ls.stop_id = st.stop_id
    JOIN raw_gtfs.stops platform ON ls.stop_id = platform.stop_id
    JOIN raw_gtfs.stops parent ON platform.parent_station = parent.stop_id
    WHERE ls.rn = 1
      AND ls.trip_id = '{trip_id}'
    ORDER BY CAST(st.stop_sequence AS INTEGER)
"""
