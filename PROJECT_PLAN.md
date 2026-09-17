# Project Plan — TfNSW Data Governance & Engineering Portfolio Project

**Prepared:** 2026-09-17, in a different Claude Code session (working directory was
`/Users/reggiealderson/Documents/2026/job_hunting`). This document is the full handoff —
read it in place of that conversation history. Everything needed to continue is below or
linked by absolute path.

**Goal:** build, in one day (today), a small, honest, hands-on project that (a) closes a
specific, real gap in Reggie's application for the NRL Senior Data Engineer – Data
Governance role, and (b) stands alone as a portfolio piece / article on
reggiealderson.com, alongside the existing TfNSW GTFS exploration already done in this repo.

---

## 1. Why this project, and why scoped this way

### 1.1 The job this targets

NRL role ad, saved at:
`/Users/reggiealderson/Documents/2026/job_hunting/applications/NRL-001/job_ad.md`

Key requirements: Databricks + Fivetran, data governance frameworks, data quality/validation,
metadata management via Unity Catalogue, privacy regulations (Australian Privacy Principles,
GDPR), DAMA-DMBOK, ISO 27001, mentoring.

Reggie's current resume/cover letter for this role:
`/Users/reggiealderson/Documents/2026/job_hunting/applications/NRL-001/Reggie_Alderson_Resume.md`
`/Users/reggiealderson/Documents/2026/job_hunting/applications/NRL-001/Reggie_Alderson_Cover_Letter.md`

There is also an interview-prep-only reference doc (talking points, not built artifacts):
`/Users/reggiealderson/Documents/2026/job_hunting/applications/NRL-001/NRL-001_dama_privacy_primer.md`

### 1.2 Gap analysis — what's already covered vs. what isn't

We audited the ad line-by-line against the resume/cover letter/experience bank:

| Ad requirement | Backed by real work history? |
|---|---|
| Databricks (Delta Lake, scheduling, clusters) | **Yes** — 2+ years production use at Pearson, explicit in resume and cover letter. **No further action needed. Do not build a Databricks component — it would be redundant with real experience, and would burn the one-day budget on a tool Reggie already knows.** |
| Python/SQL, cloud (AWS/Azure) | **Yes** — covered |
| **Dedicated data governance framework work** (not governance-as-a-byproduct-of-engineering) | **No** — cover letter explicitly admits this: "my governance experience has come through the engineering lens rather than a dedicated governance title." This is the gap. |
| **Privacy regulations applied to real personal data** (APP, GDPR) | **No** — cover letter says "privacy-aware delivery" with no concrete example |
| DAMA-DMBOK applied hands-on (not just known) | **No** — resume lists it under "Learning now" |
| Fivetran, Unity Catalogue | **No**, but explicitly decided **out of scope** for this project (see 1.3) |
| Mentoring | Not addressable by a solo project — skip |

**Conclusion: this project should focus narrowly on dedicated data governance practice —
classification, quality assurance mapped to a real framework (DAMA-DMBOK), metadata/lineage,
and privacy reasoning — applied hands-on to a real dataset for the first time.** It should
also double as a data engineering artifact (real pipeline, real dbt models, real tests), since
that's the vehicle the governance work sits on top of, and it reinforces (doesn't just repeat)
the Databricks-backed DE experience Reggie already has.

### 1.3 Explicit decisions already made (do not relitigate these)

- **No Databricks, no Unity Catalogue, no Fivetran.** Reggie does not want to spend the one
  day learning a new platform. Databricks experience is already resume-backed; Unity
  Catalogue and Fivetran are real gaps but are being knowingly deferred to keep this to a
  single day. Everything below runs on the existing local stack: **DuckDB + dbt + Python**.
- **No fabricated PII dataset.** We considered adding a synthetic "fan sign-up" table with
  fake personal data to demonstrate column masking, but decided against it — it would be
  make-believe grafted onto a transit dataset that was never going to have personal data in
  it, and a careful interviewer would see through it. Instead, the privacy angle is handled
  honestly: a documented sensitivity assessment that *concludes no PII is present, with
  reasoning* — which is itself a real, legitimate governance skill (this is what the first
  step of a Privacy Impact Assessment looks like), not a workaround.
- **Frame the write-up as a hands-on learning exercise**, not as claimed governance
  seniority. Something like: "I'd read about DAMA-DMBOK; here's what happened when I applied
  it to a real dataset for the first time." This is more credible than overclaiming, and
  matches how Reggie actually described the gap in his own cover letter.

### 1.4 Relevant background (secondary, for the article's framing only)

Reggie separately wrote a data-driven article analysing AI's impact on data-science job
titles: `/Users/reggiealderson/Documents/projects/personal_portfolio_website/src/content/articles/ai-skill-demand-data-science.mdx`.
That analysis found, for the Data Engineer role generally, that **dbt, CI/CD, and data
governance** are the fastest-rising skills 2021→2026 (dbt 2%→21%, data governance
quadrupled, CI/CD 8%→28%). This project isn't primarily about that finding — it's targeted
at the NRL ad specifically — but the article can note the connection: this project also
happens to close a gap Reggie found in his own labour-market data.

---

## 2. Current repo state — read this before writing any new code

Existing files (already exist, already verified — do not redo this exploration):

- **`DATA_FINDINGS.md`** — the single source of truth for everything learned about the GTFS
  static and realtime feeds: schema, join keys, gotchas, the dedup/confidence logic, and known
  limitations. **Read this in full before building anything.**
- **`exploration_queries.py`** — every verified query as named string constants, including
  `ESTIMATED_ACTUALS` (the exact dedup + confidence-classification logic to lift into a dbt
  model) and `ORPHAN_RATE` (the referential-integrity check to turn into a dbt test).
- **`explore_gtfs.py`** — loads the static bundle into DuckDB (`raw_gtfs.*` schema) and takes
  `n` realtime snapshots 30s apart into `raw_rt.trip_updates`, blocking, no resilience, no
  long-run capability. Columns: `feed_timestamp, entity_id, trip_id, route_id, start_date,
  trip_schedule_relationship, vehicle_id, _loaded_at, stop_sequence, stop_id, arrival_delay,
  arrival_time, departure_delay, stu_schedule_relationship`.
- **`test_poller.py`** — a smaller/older test script, takes 20 snapshots 30s apart (~10 min)
  into a *differently-shaped* table `raw_rt.poller_test` (columns: `snapshot_ts, trip_id,
  stop_id, arrival_delay, arrival_time`). **Note the schema mismatch between this and
  `explore_gtfs.py`'s `raw_rt.trip_updates`** — `snapshot_ts` vs `feed_timestamp`, fewer
  columns. `exploration_queries.py`'s `ESTIMATED_ACTUALS` query was written against the
  `poller_test` shape. Reconcile this before building the real poller (see §3).
- **`gtfs.duckdb`** — the DuckDB file from prior exploration runs. Contains the static
  bundle already. Realtime data in it so far is only short test snapshots — **not enough
  for the real project. A full collection run is required (§3).**
- **`.env`** — contains `TFNSW_API_KEY`. Already working, already authenticated.
- This directory is **not yet a git repo.** Run `git init` early (see §6).

---

## 3. The realtime polling run — how, and for how long

This is the most time-sensitive part of the plan and should be **started first, today,
before any dbt work**, because the collection run has to finish before the dbt project can
be built against real data (or the models can be scaffolded against the tiny existing
`poller_test` data first, and re-pointed at the full run once it lands — either order works,
but the poller must be *started* immediately).

### 3.1 What the existing findings tell us about the tradeoffs

From `DATA_FINDINGS.md` §3–4 (already empirically verified, do not re-derive):

- **Interval: 60 seconds.** The shortest gap between consecutive stops on a trip is ~2
  minutes, so 60-second polling guarantees every stop is seen at least once before it's
  dropped from the feed. 5-minute polling risks missing stops entirely; 10-second polling
  matches the feed's own refresh rate but just generates near-duplicate rows for no benefit.
- **Stops are dropped from the feed once a train passes them.** This is why polling frequency
  matters — miss the window and that stop's delay data is gone for good, not recoverable from
  a later snapshot.
- **"Estimated actual" vs "prediction" (the confidence field) depends on the collection
  window boundary.** A stop's delay value is classified `estimated_actual` if it was dropped
  from the feed before the *last* snapshot of the whole run (i.e., the train really did pass
  it), and `prediction` if it was still present in the final snapshot (i.e., we don't know yet
  whether the predicted delay will hold, because the train hadn't arrived when we stopped
  watching). **This means: whatever moment you choose to stop the poller, every trip still
  in progress at that instant gets studied down as lower-confidence data.** This isn't a bug —
  it's a real, documented limitation to carry into the dbt model and the write-up (see
  `DATA_FINDINGS.md` §3.7–3.8, §9.4).
- **Consequence for run length:** the *last ~1 hour* of any collection run will always be
  disproportionately full of `prediction` rows, because trips active at cutoff haven't
  finished yet. There is no way around this except stopping the run at a moment when very few
  trips are active — i.e., stop during the overnight lull, not mid-peak.

### 3.2 The plan: one continuous ~24–26 hour run, started now, stopped in a quiet window

1. **Start the poller as close to "now" as possible today.** It needs to run unattended for
   roughly a full day, so the earlier it starts, the more comfortably it finishes by
   tomorrow's work session.
2. **Run continuously at a 60-second interval.**
3. **Target duration: 24–26 hours**, so the collection spans one full weekday service day
   (both peaks, both off-peaks) with margin. A shorter run (e.g. just a few hours) would only
   support "which routes are worst right now"-type analysis, not the fuller "does delay
   accumulate through a trip", "is morning peak worse than evening peak" questions
   `DATA_FINDINGS.md` §7 says the project can answer — and those richer questions are what
   make the resulting quality tests and analysis meaningful.
4. **Deliberately end the run in the overnight low-traffic window (roughly 02:00–04:00 AEST),
   not mid-peak.** Very few trips are active then, so the boundary effect in §3.1 is minimised
   — only a handful of trips will be marked `prediction` due to cutoff timing, instead of an
   entire evening peak's worth. Concretely: if the poller starts today in the afternoon/evening,
   let it run through the next full day and stop it in the small hours after that, once
   activity has dropped off — do not just stop it at the 24-hour mark automatically if that
   lands during peak.
5. **A single weekday run is the scope for this project** — do not also try to capture a
   weekend for comparison. That "weekday vs weekend" question from `DATA_FINDINGS.md` §7 is
   explicitly out of scope; note it as a documented limitation / future extension in the
   write-up, not something to build today.

### 3.3 The poller script itself needs to be built (not reused as-is)

Neither existing script is fit for a 24-hour unattended run:

- `test_poller.py` only takes a fixed 20 snapshots and stops — no continuous/long-run mode.
- `explore_gtfs.py`'s `load_rt()` similarly takes a fixed `n` snapshots in one blocking call —
  fine for a 10-minute test, not for a day-long run — and it holds everything in memory
  (`frames = []`, concatenated once at the end), which means a crash partway through loses
  the *entire* run's data.

Build a new, small, dedicated long-poller script (e.g. `poll_rt.py`) with these properties:

- Runs in a loop indefinitely (or until a max-duration/max-snapshots argument is hit),
  sleeping 60 seconds between calls.
- **Writes each snapshot to disk immediately** (e.g. `INSERT INTO raw_rt.trip_updates ...`
  after every fetch, or appends to a Parquet/CSV file per snapshot) rather than accumulating
  in memory — so a crash at hour 20 doesn't lose hours 1–20.
- **Logs gaps**: if a fetch fails or takes unusually long, log it clearly (timestamp,
  error). `DATA_FINDINGS.md` §4 already notes "the poller should log gaps and the dbt model
  should account for them" — this is a known, accepted limitation, not something to solve,
  just something to be visible about.
- Uses **one consistent schema** — align on the `explore_gtfs.py` `fetch_rt_snapshot()` shape
  (it's the richer one — keeps `route_id`, `trip_schedule_relationship`, cancelled-trip rows
  with no stop updates, etc.) rather than `test_poller.py`'s narrower shape. Write into
  `raw_rt.trip_updates`, appending across the whole run (not `CREATE OR REPLACE` per
  snapshot — that would delete prior snapshots each time).
- Can be run with `nohup python poll_rt.py > poll.log 2>&1 &` or similar so it survives the
  terminal session closing, since it needs to run overnight.
- Sanity-check it briefly (a minute or two) before committing to the full run, to confirm rows
  are landing correctly and the API key/auth still works.

**Do this first, today, before anything else in this plan**, since it's the long pole.

---

## 4. dbt project — the data engineering backbone

Once the poller is running (doesn't need to wait for it to finish — can scaffold against
the small existing `poller_test`/`trip_updates` data and re-run against the full dataset once
collection completes):

1. **`dbt init`** in this repo, profile pointed at `gtfs.duckdb`.
2. **Staging models:**
   - `stg_gtfs__stop_times` — cast `arrival_time`/`departure_time` from text; document (don't
     "fix") the past-midnight (`25:10:00`) gotcha from `DATA_FINDINGS.md` §2.6.
   - `stg_gtfs__stops` — parent/child station structure; filter `parent_station IS NOT NULL
     AND parent_station != ''` (empty string, not NULL — §5 gotcha table).
   - `stg_rt__trip_updates` — cast `feed_timestamp`/snapshot timestamps to proper timestamps
     with `AT TIME ZONE 'Australia/Sydney'`.
3. **Intermediate model — `int_rt__latest_update`:** the dedup + confidence-classification
   logic, lifted directly from `exploration_queries.py`'s `ESTIMATED_ACTUALS` /
   `DATA_FINDINGS.md` §3.6–3.7 (`ROW_NUMBER() OVER (PARTITION BY trip_id, stop_id ORDER BY
   snapshot_ts DESC)`, then compare each stop's last-seen timestamp to the global max
   timestamp of the run to set `confidence = 'estimated_actual' | 'prediction'`).
4. **Mart — `fct_stop_delays`:** join through to the **parent station** (never the raw
   platform-level stop) for readable names, per `DATA_FINDINGS.md` §2.5 and the `CORE_JOIN`
   query pattern in `exploration_queries.py`.

---

## 5. Governance layer — the actual point of the project

Layer this directly on top of the dbt project above; don't treat it as a separate track.

### 5.1 dbt tests, explicitly mapped to DAMA-DMBOK's data quality dimensions

Write these as real dbt tests (`schema.yml`), and afterwards produce a short **data quality
scorecard** (one table: dimension → test → result → what it means) as a governance artifact
in its own right:

| DAMA dimension | Test |
|---|---|
| Completeness | `not_null` on key fields (`trip_id`, `stop_id`, `arrival_delay` in the mart) |
| Uniqueness | `unique` (or `dbt_utils.unique_combination_of_columns`) on `(trip_id, stop_id)` in `fct_stop_delays` |
| Validity | `accepted_values` on `confidence` — only `prediction` / `estimated_actual` allowed |
| Referential integrity | `relationships` test, realtime `trip_id` → static `trips.trip_id` (this is the `ORPHAN_RATE` query from `exploration_queries.py`, turned into a proper test — verified 0 orphans out of 448 trips previously, per `DATA_FINDINGS.md` §3.2) |
| Timeliness | A freshness-style test/check that snapshot timestamps are recent/contiguous relative to the intended 60s cadence — surface any gaps the poller logged (§3.3) |
| Consistency | A test that `arrival_delay` values fall within a sane range (catches unit or sign errors — e.g. reject anything more than a few hours either way) |

### 5.2 Classification / sensitivity assessment (the privacy artifact)

Write a short, explicit document (or a `docs/classification.md` in this repo) that goes table
by table (`stops`, `trips`, `stop_times`, `trip_updates`, and the final mart) and states:

- The classification (`public` in every case here, per `DATA_FINDINGS.md` §8).
- **The reasoning**, not just the label: no individual passenger is identifiable, no field
  contains personal information, this is aggregate schedule and delay data only.
- Explicitly frame this as a **mini Privacy Impact Assessment** — "I assessed each table
  against the Australian Privacy Principles' definition of personal information and found
  none present, for these reasons..." This is a real, honest way to demonstrate privacy-
  regulation literacy without needing an actual PII dataset (see §1.3's reasoning for why we
  are not fabricating one).

### 5.3 Metadata / lineage (via `dbt docs generate`)

Run `dbt docs generate` (and `dbt docs serve` to check it) once models and `schema.yml`
descriptions are in place. This produces, essentially for free:

- A lineage graph (DAG) of staging → intermediate → mart — screenshot this for the article.
- A data dictionary — port the column-level knowledge already written up in
  `DATA_FINDINGS.md` (e.g. what `stop_sequence` means, why it's NULL in realtime data, what
  `confidence` means) into `schema.yml` `description:` fields so they surface in the docs
  site. This is largely a formatting/porting exercise, not new analysis — the content already
  exists.

### 5.4 Short governance/policy note

Half a page covering:

- **Retention / change management**: the static bundle has no version number or changelog
  (`DATA_FINDINGS.md` §2.8) — document this as an accepted risk, and state what a production
  system would do differently (daily diffing).
- **Ownership**: who would be the data steward for this dataset if it were a team project.
- **Known limitations**, reframed as documented risk acknowledgement rather than just
  caveats — lift directly from `DATA_FINDINGS.md` §9 (no actual arrival times, prediction
  fluctuation up to 70s, polling gaps, collection-boundary effect, no static versioning,
  `stop_sequence` unreliability).

---

## 6. Repo hygiene

- `git init` this repo today, before or alongside the work (currently not a git repo).
- Add a `.gitignore` covering `.venv/`, `gtfs.duckdb` (or decide if a sample/subset should be
  committed — likely not, it'll be large), `.env` (contains the API key — **never commit
  this**).
- Commit incrementally (poller script, then dbt scaffold, then each model, then tests, then
  docs) — the commit history itself is a small piece of evidence of process discipline, which
  is relevant to a governance-adjacent role.

---

## 7. Article

Write for reggiealderson.com, honest framing throughout:

- "I'd read about DAMA-DMBOK for an application; here's what happened when I applied it
  hands-on, for the first time, to a real dataset."
- Walk through: the quality-dimension test mapping (§5.1), the classification/PIA-lite
  exercise (§5.2) — including being explicit that concluding "no PII present, here's why" is
  itself the governance skill being demonstrated, not a workaround — and the lineage/metadata
  output (§5.3).
- Be upfront about scope boundaries: this is a public, non-personal dataset, run on a local
  stack, not an enterprise platform — name Databricks/Unity Catalogue/Fivetran as the pieces
  deliberately deferred, and why (already resume-backed / genuinely out of one-day scope).
  This kind of honesty about scope is a better signal than overclaiming.
- Optionally note the connection to the separate skill-demand article's finding that
  governance/dbt/CI-CD are the fastest-rising Data Engineer skills 2021→2026 (§1.4) — but
  keep this secondary; the primary frame is the NRL-specific gap.

---

## 8. Priority order / cut line for the one-day budget

1. **Start the poller (§3) — first thing, non-negotiable, it's the long pole.**
2. dbt staging + intermediate + mart models (§4) — non-negotiable, this is the DE evidence.
3. DAMA-mapped dbt tests + scorecard (§5.1) — non-negotiable, this is the core governance
   artifact.
4. Classification / PIA-lite writeup (§5.2) — non-negotiable, this is the privacy artifact.
5. `dbt docs` lineage/dictionary (§5.3) — keep if time allows; cheap since the content mostly
   already exists in `DATA_FINDINGS.md`.
6. Governance/policy note (§5.4) — first thing to trim if short on time; its content can
   instead just be summarised/linked from `DATA_FINDINGS.md` §9 directly in the article.
7. Article (§7) — write last, once the artifacts above exist to describe honestly.

Weekend-vs-weekday comparison, Fivetran, Unity Catalogue, and Databricks are all explicitly
**out of scope** — do not let the conversation drift back into them (see §1.3).
