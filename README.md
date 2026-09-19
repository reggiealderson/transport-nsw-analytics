# Tracking a day of Sydney trains

A small, end-to-end data project built on Transport for NSW's public train feeds. It collects a
weekday of live train data, models it with dbt into clean, analysis-ready tables, applies a layer of
data-governance practices (quality tests, a data classification, lineage, and a policy note), and
uses the result to measure how punctual the network was.

The stack is deliberately small and runs on a single machine: **Python + DuckDB + dbt**.

**Write-up:** [reggiealderson.com/articles/tracking-a-day-of-sydney-trains](https://reggiealderson.com/articles/tracking-a-day-of-sydney-trains)

---

## What it does

Transport for NSW publishes two GTFS feeds for Sydney Trains: a **static** feed (the timetable) and
a **realtime** feed (live trip updates). The pipeline:

1. **Collects** the realtime feed every 60 seconds for ~24–36 hours (`poll_rt.py`), writing each
   snapshot to DuckDB immediately so a long run survives interruptions.
2. **Transforms** the raw snapshots with dbt (`dbt/`) through staging → intermediate → mart layers,
   reducing the many snapshots of each stop to a single best estimate of its delay and labelling it
   `estimated_actual` or `prediction`.
3. **Tests and documents** the result: a suite of dbt tests mapped to the DAMA-DMBOK data-quality
   dimensions, a data classification, and a generated data dictionary + lineage graph.

The core measurement is simple: **delay = observed stop time − scheduled stop time**, per train, per
stop. Most of the work is turning a live, quirky feed into a reliable version of that one number.

## Key findings (one Friday)

- 97.5% of arrivals were within five minutes of the timetable; 20.8% were more than 30 seconds late.
- Delay accumulates over a journey — average delay roughly doubled from the start of a trip to the end.
- The midday off-peak was less punctual than either rush hour.
- The long-distance intercity lines were most likely to run at least one late stop, driven by
  distance rather than the number of stops.

## Repo layout

```
poll_rt.py                 # the long-running realtime collector (writes to gtfs.duckdb)
explore_gtfs.py            # loads the static GTFS timetable into gtfs.duckdb
make_charts.py             # generates the article's data charts (theme-aware SVG)
make_diagrams.py           # generates the hero, pipeline, and governance diagrams

dbt/
  models/staging/          # one model per raw table: casts, renames, gotcha handling
  models/intermediate/     # dedup to last-seen reading + confidence; trip instances
  models/marts/            # fct_stop_delays, fct_trip_punctuality
  tests/                   # custom timeliness + consistency tests

docs/
  classification.md        # privacy threshold assessment (APP / GDPR) — concludes public, no PII
  quality_scorecard.md     # DAMA dimension → test → result → meaning
  governance_note.md       # ownership, change management, limitations, multi-day soundness

DATA_FINDINGS.md           # everything learned about the feeds (schema, join keys, gotchas)
```

## How the data behaves (the important quirks)

These are the properties that shaped the design; there is much more in `DATA_FINDINGS.md`.

- **Stops drop out of the feed as trains pass them.** The realtime feed only describes what is still
  ahead of each train, so it never reports a confirmed actual time. The best estimate of a stop's
  real delay is the last prediction recorded before that stop disappeared.
- **A `trip_id` is not unique across days.** The same service reuses its id daily, so the real key
  is `trip_id + service_date`. (A uniqueness test that ignored this passed while silently merging
  two days' runs — the models now key on the full combination.)
- **The feed omits the service date** (`start_date` is empty), so it is derived from each request's
  timestamp.
- **The static timetable regenerates its `trip_id`s nightly.** A single downloaded bundle matches
  its own day's realtime feed but not the next day's — which is why analysis is scoped to one day.

## Running it yourself

Requires Python 3 and a free TfNSW Open Data API key
([opendata.transport.nsw.gov.au](https://opendata.transport.nsw.gov.au)).

```bash
python -m venv .venv && source .venv/bin/activate
pip install requests duckdb gtfs-realtime-bindings pandas pytz dbt-duckdb

echo 'TFNSW_API_KEY=your-key-here' > .env
set -a && . ./.env && set +a          # export the key into the shell

# 1. load the static timetable into gtfs.duckdb
python explore_gtfs.py --snapshots 1

# 2. collect the realtime feed (runs in the background; stop it in a quiet overnight window)
nohup python poll_rt.py --interval 60 --max-hours 36 > poll.log 2>&1 &

# 3. build and test the dbt models (run from the dbt/ directory)
cd dbt && dbt build --profiles-dir .

# 4. (optional) regenerate the charts and diagrams
cd .. && python make_charts.py && python make_diagrams.py
```

dbt reads `gtfs.duckdb` read-only and writes its models to a separate `analytics.duckdb`, so it
never contends with the collector for the database lock.

## Notes and limitations

- This is a one-day, single-weekday sample on a public, non-personal dataset. It's a learning and
  portfolio project, not a production system.
- The `confidence` column marks which delay readings are settled estimates and which are still open
  predictions. Any train mid-journey when collection stops keeps `prediction` readings.
- Cloud platforms (Databricks, Unity Catalogue, Fivetran) are intentionally not used; the same
  governance work would apply on any of them.
- Extending to multiple days would need two changes: versioning the timetable per day, and a
  confidence rule that works for a feed that never stops. See `docs/governance_note.md`.

## Data source and licence

Data from the [Transport for NSW Open Data Hub](https://opendata.transport.nsw.gov.au), used under
its terms. Line names and colours are from the TfNSW Open Data Hub and Wikipedia.
