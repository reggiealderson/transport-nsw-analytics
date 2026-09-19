# Governance & policy note

**Dataset:** TfNSW Sydney Trains GTFS (static) + GTFS-Realtime (trip updates)
**Scope:** the local DuckDB + dbt pipeline in this repo
**Companion docs:** `docs/classification.md` (privacy threshold assessment),
`DATA_FINDINGS.md` (empirical findings), the dbt `schema.yml` files (tests + metadata).

This is the half-page policy layer that sits over the pipeline: who owns the data, how
change and retention are handled, and which risks are knowingly accepted. It is written
at the altitude a small team would actually use — enough to act on, not a 40-page
framework document.

---

## 1. Ownership & stewardship

In a team setting this dataset would have a named **data steward** accountable for it.
For this solo portfolio build, that role is held by the author (Reggie Alderson); the
table below records what the role *is*, so it is transferable rather than implicit.

| Role | Who | Accountable for |
|---|---|---|
| **Data steward** | Reggie Alderson (solo) | Classification stays correct; the change-management trigger (§2) is honoured; quality tests are watched, not just run. |
| **Data owner** (upstream) | Transport for NSW | The source feeds' content, licensing, and availability. Out of our control; consumed under the TfNSW Open Data licence. |
| **Pipeline maintainer** | Reggie Alderson (solo) | The dbt models, the poller, and the DuckDB store. |

Separating **owner** (TfNSW, upstream) from **steward** (us, for our copy and
derivations) matters: we cannot fix source data, but we are accountable for how we
classify, transform, test, and document it downstream.

---

## 2. Change management & retention

### Static bundle — no versioning (accepted risk)
The static GTFS bundle carries **no version number and no changelog**
(`DATA_FINDINGS.md` §2.8). TfNSW republishes it daily (~01:30 AEST); a renamed route, a
new platform, or an altered timetable appears **silently** in the next day's bundle.

- **Decision for this project:** download the bundle **once** and treat it as valid for
  the whole collection run. This is a knowingly **accepted risk** — the run is ~24-26h,
  well inside a single daily bundle's validity, so drift is not a practical concern here.
- **What production would do differently:** download the bundle daily, **diff it against
  the previous day** (row-level hash or key-set comparison per table), and alert on
  unexpected schema or key changes before they flow downstream. Store each day's bundle
  keyed by ingest date so a realtime snapshot can always be joined to the schedule that
  was actually in force when it was collected.

### Is this methodology sound for MULTI-day analysis?

A methodology should be judged not just on today's one-day run but on whether it survives
being scaled to weeks or months of data. Assessed on that basis:

**What already transfers cleanly (designed for it):**
- **Trip identity** — the composite key `trip_id + service_date`, and the derived
  `service_date` (3am service-day boundary). This exists *specifically* so the same `trip_id`
  on different days is never conflated. (We proved the failure it prevents: 518 `trip_id`s
  recurred across just two days.)
- **Dedup grain, the three start-times, and the marts** are all keyed per instance, and the
  24-hour scope is applied as a *filter* rather than baked into the models — so a rolling,
  multi-day window needs no re-modelling.

**What does NOT transfer as built (must change before multi-day use):**
- **Static-schedule ingestion — the blocker.** We download the bundle once. Because TfNSW
  regenerates `trip_id`s each daily republish, a single bundle only matches its *own* day
  (empirically: Friday 98.3% match, Saturday 12.4%). Any multi-day pipeline **must** ingest
  and version the bundle *per day* and join each service date's realtime to the schedule that
  was in force that day. This is the single biggest change required.
- **Confidence classification.** `estimated_actual` vs `prediction` is currently decided by
  comparing a stop's last sighting to the **global maximum snapshot of the whole batch**. That
  is correct for a bounded one-off run, but wrong for a continuous pipeline, where "the end of
  the run" is not a meaningful point. A rolling system needs a different rule — e.g. a stop is
  `estimated_actual` once its trip has completed / it has been absent for N snapshots.
- **Load strategy.** Models here fully rebuild each run. Over months that becomes slow and
  wasteful; a production version would materialise **incrementally**, partitioned by
  `service_date`.

The takeaway for the write-up: the *dimensional modelling* is multi-day-ready by design, but
the *ingestion and confidence logic* are deliberate one-run simplifications that would be
re-engineered before scaling. Naming that distinction precisely is itself the governance skill.

### Realtime data — retention
Realtime snapshots are appended to `raw_rt.trip_updates` and kept for the life of the
run (see the size projection in the poller notes: ~5M rows / a few hundred MB for a
day). There is **no automated retention/expiry** on the local store — acceptable for a
one-off analysis; a production system would set a retention window and archive or roll
off older snapshots (e.g. keep raw snapshots 30 days, keep the derived `fct_stop_delays`
mart indefinitely).

### Change-management trigger (links to the PIA-lite)
`docs/classification.md` §5 lists the events that would change the **privacy**
classification (joining to Opal/ticketing, CCTV/Wi-Fi counting, or a populated
`vehicle_id`). Operationally, that list is a **gate**: introducing a new source or
joining two datasets requires re-running the classification threshold assessment
*before* the new data is published downstream. For a solo project this is a checklist
habit; on a team it would be a required step in the change/PR process.

---

## 3. Known limitations — accepted, and documented as risk

These are lifted from `DATA_FINDINGS.md` §9 and reframed as **explicit risk
acknowledgement** — they are known and accepted for this project's scope, not hidden
caveats. Each notes how it is surfaced or what it means for interpretation.

| # | Limitation | Status / how it's handled |
|---|---|---|
| 1 | **No true actual arrival times.** Every delay is a prediction; the feed never labels a value "actual." Our "estimated actual" is the *last observed* prediction before a stop dropped from the feed. | Accepted & modelled: exposed as the `confidence` column (`estimated_actual` vs `prediction`) in `int_rt__latest_update` / `fct_stop_delays`. Interpret `estimated_actual` as "best available", not "measured". |
| 2 | **Prediction fluctuation** — delay values can move up to ~70s even in the final snapshots before arrival. | Accepted: inherent feed noise. Bounds the precision of any single delay figure; use aggregates, not one row, for conclusions. |
| 3 | **Polling gaps** — any period the poller isn't running loses that window's trips entirely. | Made visible: the poller logs gaps, and the `assert_snapshot_cadence` dbt test (warn) flags any interval > 150s. Not silently absorbed. |
| 4 | **Collection-boundary effect** — trips still running at cutoff get their later stops marked `prediction`, not `estimated_actual`; trips starting after cutoff are absent. | Mitigated by design: the run is stopped in the overnight lull (~02:00-04:00), when few trips are active, minimising the affected tail. Documented as a limitation regardless. |
| 5 | **Static bundle versioning** — see §2. | Accepted risk (single-bundle assumption); production mitigation described in §2. |
| 6 | **`stop_sequence` unreliable in realtime** — always NULL in the RT feed. | Handled: never used as a join key; realtime↔static joins are on `trip_id` + `stop_id` (verified 0 orphans). |
| 7 | **Scope boundaries** — one weekday only (no weekend comparison); local DuckDB/dbt stack, not an enterprise platform (Databricks / Unity Catalogue / Fivetran deliberately deferred). | Intentional scope decision, not an oversight. Weekend-vs-weekday is a documented future extension. |

---

## 4. Summary

The data is **public** (per the PIA-lite), owned upstream by TfNSW and stewarded locally
by the author. The two governance risks that actually matter here — **silent static-data
drift** and **lossy/low-confidence realtime data at the collection boundary** — are both
knowingly accepted for a one-day analysis, mitigated where cheap (overnight cutoff, gap
logging, confidence labelling), and paired with a clear statement of what a production
system would do instead. Nothing is swept under the rug; the limitations are part of the
deliverable.
