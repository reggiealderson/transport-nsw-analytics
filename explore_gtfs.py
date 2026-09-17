"""
Explore TfNSW Sydney Trains GTFS (static) + GTFS-Realtime (trip updates) in DuckDB.

Setup:
    pip install requests duckdb gtfs-realtime-bindings pandas
    export TFNSW_API_KEY="your-key"          # Windows: set TFNSW_API_KEY=...
    python explore_gtfs.py                   # add --snapshots 5 to grab several RT snapshots

Then explore:
    duckdb gtfs.duckdb          (or `duckdb -ui gtfs.duckdb` for the browser UI)

Endpoints below are the v2 Sydney Trains feeds. Confirm them on the Open Data Hub
(opendata.transport.nsw.gov.au) and override with env vars if they've changed.
"""
import argparse, io, os, sys, time, zipfile
from datetime import datetime, timezone

import duckdb, pandas as pd, requests
from google.transit import gtfs_realtime_pb2

KEY = os.environ.get("TFNSW_API_KEY") or sys.exit("Set TFNSW_API_KEY first.")
STATIC_URL = os.environ.get("STATIC_URL", "https://api.transport.nsw.gov.au/v1/gtfs/schedule/sydneytrains")
RT_URL = os.environ.get("RT_URL", "https://api.transport.nsw.gov.au/v2/gtfs/realtime/sydneytrains")
HEADERS = {"Authorization": f"apikey {KEY}"}
DB = "gtfs.duckdb"


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=120)
    if r.status_code != 200:
        sys.exit(f"{r.status_code} from {url}: {r.text[:300]}")
    return r.content


def load_static(con):
    print("Downloading static GTFS bundle...")
    z = zipfile.ZipFile(io.BytesIO(get(STATIC_URL)))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw_gtfs")
    for name in z.namelist():
        if not name.endswith(".txt"):
            continue
        table = name[:-4]
        # Read everything as text: GTFS times like 25:10:00 aren't valid TIMEs.
        df = pd.read_csv(z.open(name), dtype=str, keep_default_na=False)
        con.execute(f"CREATE OR REPLACE TABLE raw_gtfs.{table} AS SELECT * FROM df")
        print(f"  raw_gtfs.{table:<16} {len(df):>9,} rows")


def fetch_rt_snapshot():
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(get(RT_URL))
    loaded_at = datetime.now(timezone.utc)
    rows = []
    for ent in feed.entity:
        if not ent.HasField("trip_update"):
            continue
        tu = ent.trip_update
        base = {
            "feed_timestamp": feed.header.timestamp,
            "entity_id": ent.id,
            "trip_id": tu.trip.trip_id,
            "route_id": tu.trip.route_id,
            "start_date": tu.trip.start_date,
            "trip_schedule_relationship": gtfs_realtime_pb2.TripDescriptor.ScheduleRelationship.Name(
                tu.trip.schedule_relationship),
            "vehicle_id": tu.vehicle.id,
            "_loaded_at": loaded_at,
        }
        if not tu.stop_time_update:  # e.g. cancelled trips carry no stop updates
            rows.append(base)
        for stu in tu.stop_time_update:
            rows.append({
                **base,
                "stop_sequence": stu.stop_sequence if stu.HasField("stop_sequence") else None,
                "stop_id": stu.stop_id,
                "arrival_delay": stu.arrival.delay if stu.HasField("arrival") else None,
                "arrival_time": stu.arrival.time if stu.HasField("arrival") else None,
                "departure_delay": stu.departure.delay if stu.HasField("departure") else None,
                "stu_schedule_relationship": gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.ScheduleRelationship.Name(
                    stu.schedule_relationship),
            })
    return pd.DataFrame(rows)


def load_rt(con, n):
    con.execute("CREATE SCHEMA IF NOT EXISTS raw_rt")
    frames = []
    for i in range(n):
        df = fetch_rt_snapshot()
        print(f"RT snapshot {i + 1}/{n}: {df['trip_id'].nunique()} trips, {len(df):,} stop updates")
        frames.append(df)
        if i < n - 1:
            time.sleep(30)
    all_rt = pd.concat(frames, ignore_index=True)
    con.execute("CREATE OR REPLACE TABLE raw_rt.trip_updates AS SELECT * FROM all_rt")


STARTER_QUERIES = {
    "Route types and counts": """
        SELECT route_type, count(*) AS routes FROM raw_gtfs.routes GROUP BY 1 ORDER BY 2 DESC""",
    "GTFS times past midnight (the service-day gotcha)": """
        SELECT arrival_time, count(*) AS n FROM raw_gtfs.stop_times
        WHERE arrival_time >= '24:00:00' GROUP BY 1 ORDER BY 1 LIMIT 5""",
    "RT schedule relationships": """
        SELECT trip_schedule_relationship, count(DISTINCT trip_id) AS trips
        FROM raw_rt.trip_updates GROUP BY 1""",
    "Orphan rate: RT trips missing from the static schedule": """
        SELECT count(DISTINCT r.trip_id) AS rt_trips,
               count(DISTINCT r.trip_id) FILTER (WHERE t.trip_id IS NULL) AS orphans
        FROM raw_rt.trip_updates r LEFT JOIN raw_gtfs.trips t USING (trip_id)""",
    "Current delay distribution (minutes)": """
        SELECT round(arrival_delay / 60) AS delay_min, count(*) AS n
        FROM raw_rt.trip_updates WHERE arrival_delay IS NOT NULL
        GROUP BY 1 ORDER BY 1""",
}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshots", type=int, default=1, help="RT snapshots to take, 30s apart")
    ap.add_argument("--skip-static", action="store_true")
    args = ap.parse_args()

    con = duckdb.connect(DB)
    if not args.skip_static:
        load_static(con)
    load_rt(con, args.snapshots)

    for title, sql in STARTER_QUERIES.items():
        print(f"\n== {title} ==")
        try:
            print(con.sql(sql).df().to_string(index=False))
        except Exception as e:
            print(f"  (skipped: {e})")
    print(f"\nDone. Explore with: duckdb -ui {DB}")
