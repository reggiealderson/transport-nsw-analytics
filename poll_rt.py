"""
Long-running GTFS-Realtime poller for TfNSW Sydney Trains trip updates.

Purpose: collect one continuous ~24-26h weekday service day of realtime trip
updates at a 60s cadence into gtfs.duckdb -> raw_rt.trip_updates, resiliently
enough to survive the terminal closing, a crash, or a transient API failure.

Design (see PROJECT_PLAN.md §3.3 and DATA_FINDINGS.md §3-4):
  - Loops on a fixed interval (default 60s) until --max-hours is hit or it's
    stopped (Ctrl-C / kill). No fixed snapshot count.
  - Writes EACH snapshot to disk immediately (INSERT ... then checkpoint), so a
    crash at hour 20 keeps hours 1-20. Nothing is buffered in memory across snapshots.
  - Appends across the whole run into raw_rt.trip_updates (never CREATE OR REPLACE).
  - Uses the richer explore_gtfs.py snapshot shape (keeps route_id, cancelled-trip
    rows, etc.). Column types are fixed up front so per-snapshot dtype drift can't
    break an INSERT mid-run.
  - Logs every snapshot, every failure, and any gap where the real elapsed time
    between successful snapshots exceeds the interval (accepted limitation, made visible).
  - Opens/closes the DuckDB connection per snapshot, so the file is only locked for
    the ~1s of each write and can be safely inspected read-only between snapshots.

Usage:
    export TFNSW_API_KEY=...              # or rely on .env being exported
    nohup .venv/bin/python poll_rt.py > poll.log 2>&1 &

    # short sanity check before committing to the full run:
    .venv/bin/python poll_rt.py --max-hours 0.05   # ~3 minutes
"""
import argparse
import os
import signal
import sys
import time
from datetime import datetime, timezone

import duckdb
import pandas as pd
import requests
from google.transit import gtfs_realtime_pb2

KEY = os.environ.get("TFNSW_API_KEY") or sys.exit("Set TFNSW_API_KEY first.")
RT_URL = os.environ.get("RT_URL", "https://api.transport.nsw.gov.au/v2/gtfs/realtime/sydneytrains")
HEADERS = {"Authorization": f"apikey {KEY}"}
DB = os.environ.get("DB", "gtfs.duckdb")
TABLE = "raw_rt.trip_updates"

# Canonical column order + types. Fixed here so the INSERT is identical every
# snapshot regardless of what pandas infers from a given batch of rows.
COLUMNS = {
    "feed_timestamp": "BIGINT",
    "entity_id": "VARCHAR",
    "trip_id": "VARCHAR",
    "route_id": "VARCHAR",
    "start_date": "VARCHAR",
    "trip_schedule_relationship": "VARCHAR",
    "vehicle_id": "VARCHAR",
    "_loaded_at": "TIMESTAMP WITH TIME ZONE",
    "stop_sequence": "DOUBLE",
    "stop_id": "VARCHAR",
    "arrival_delay": "DOUBLE",
    "arrival_time": "DOUBLE",
    "departure_delay": "DOUBLE",
    "stu_schedule_relationship": "VARCHAR",
}


def log(msg):
    """Timestamped, immediately-flushed log line (survives nohup redirection)."""
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"[{ts}] {msg}", flush=True)


def fetch_rt_snapshot():
    """One realtime snapshot -> DataFrame in the canonical column shape."""
    r = requests.get(RT_URL, headers=HEADERS, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(r.content)
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
    # Guarantee every column exists and is in canonical order.
    return pd.DataFrame(rows).reindex(columns=list(COLUMNS))


def ensure_table():
    """Create raw_rt schema + trip_updates (if missing) with fixed types.
    Never drops or replaces existing data — appends only."""
    con = duckdb.connect(DB)
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw_rt")
        cols_ddl = ",\n            ".join(f"{name} {typ}" for name, typ in COLUMNS.items())
        con.execute(f"CREATE TABLE IF NOT EXISTS {TABLE} (\n            {cols_ddl}\n        )")
        n = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
        return n
    finally:
        con.close()


def write_snapshot(df):
    """Append one snapshot to disk immediately, with explicit casts, then checkpoint."""
    select_list = ",\n            ".join(f"CAST({name} AS {typ}) AS {name}" for name, typ in COLUMNS.items())
    con = duckdb.connect(DB)
    try:
        con.register("snap_df", df)
        con.execute(f"INSERT INTO {TABLE}\n        SELECT\n            {select_list}\n        FROM snap_df")
        con.execute("CHECKPOINT")  # flush WAL to the main file so a crash keeps this snapshot
    finally:
        con.close()


_stop = False


def _handle_signal(signum, frame):
    global _stop
    _stop = True
    log(f"Received signal {signum} — will stop cleanly after the current snapshot.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--interval", type=float, default=60.0, help="seconds between snapshots (default 60)")
    ap.add_argument("--max-hours", type=float, default=36.0,
                    help="safety cap; stop after this many hours (default 36). "
                         "Intended to be stopped manually in the overnight lull well before this.")
    args = ap.parse_args()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    existing = ensure_table()
    start = time.monotonic()
    deadline = start + args.max_hours * 3600
    log(f"POLLER START — db={DB} table={TABLE} interval={args.interval}s max_hours={args.max_hours}")
    log(f"Table already holds {existing:,} rows before this run; appending.")

    snap_no = 0
    ok = 0
    fails = 0
    consecutive_fails = 0
    total_rows = 0
    last_success_mono = None

    while not _stop and time.monotonic() < deadline:
        cycle_start = time.monotonic()
        snap_no += 1
        try:
            df = fetch_rt_snapshot()
            write_snapshot(df)
            ok += 1
            consecutive_fails = 0
            total_rows += len(df)
            trips = df["trip_id"].nunique()
            elapsed_h = (time.monotonic() - start) / 3600
            # Make polling gaps visible (accepted limitation, per DATA_FINDINGS §4).
            gap_note = ""
            if last_success_mono is not None:
                gap = time.monotonic() - last_success_mono
                if gap > args.interval * 1.5:
                    gap_note = f"  ** GAP {gap:.0f}s since last success (expected ~{args.interval:.0f}s) **"
            last_success_mono = time.monotonic()
            log(f"snapshot {snap_no}: OK  trips={trips:,} rows={len(df):,}  "
                f"cum_rows={total_rows:,}  ok={ok} fails={fails}  elapsed={elapsed_h:.2f}h{gap_note}")
        except Exception as e:
            fails += 1
            consecutive_fails += 1
            log(f"snapshot {snap_no}: FAIL ({consecutive_fails} in a row) — {type(e).__name__}: {e}")

        if _stop:
            break
        # Sleep the remainder of the interval (account for fetch/write time), stay responsive to signals.
        sleep_left = args.interval - (time.monotonic() - cycle_start)
        while sleep_left > 0 and not _stop:
            time.sleep(min(1.0, sleep_left))
            sleep_left = args.interval - (time.monotonic() - cycle_start)

    total_h = (time.monotonic() - start) / 3600
    log(f"POLLER STOP — ran {total_h:.2f}h  snapshots_attempted={snap_no} ok={ok} fails={fails}  "
        f"rows_this_run={total_rows:,}")


if __name__ == "__main__":
    main()
