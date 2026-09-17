"""Collect ~10 minutes of RT snapshots for empirical testing."""
import os, sys, time
from datetime import datetime, timezone
import duckdb, pandas as pd, requests
from google.transit import gtfs_realtime_pb2

KEY = os.environ.get("TFNSW_API_KEY") or sys.exit("Set TFNSW_API_KEY first.")
RT_URL = os.environ.get("RT_URL", "https://api.transport.nsw.gov.au/v2/gtfs/realtime/sydneytrains")
HEADERS = {"Authorization": f"apikey {KEY}"}

def fetch():
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(requests.get(RT_URL, headers=HEADERS, timeout=30).content)
    rows = []
    for ent in feed.entity:
        if not ent.HasField("trip_update"):
            continue
        tu = ent.trip_update
        for stu in tu.stop_time_update:
            rows.append({
                "snapshot_ts": feed.header.timestamp,
                "trip_id": tu.trip.trip_id,
                "stop_id": stu.stop_id,
                "arrival_delay": stu.arrival.delay if stu.HasField("arrival") else None,
                "arrival_time": stu.arrival.time if stu.HasField("arrival") else None,
            })
    return pd.DataFrame(rows)

frames = []
for i in range(20):
    df = fetch()
    n_trips = df["trip_id"].nunique()
    print(f"Snapshot {i+1}/20  —  {n_trips} trips, {len(df)} rows")
    frames.append(df)
    if i < 19:
        time.sleep(30)

all_data = pd.concat(frames, ignore_index=True)
con = duckdb.connect("gtfs.duckdb")
con.execute("CREATE OR REPLACE TABLE raw_rt.poller_test AS SELECT * FROM all_data")
print(f"\nDone. {len(all_data)} total rows saved to raw_rt.poller_test")