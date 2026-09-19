# Data quality scorecard

## What this document is

This is a **data-quality scorecard**: a one-page, human-readable summary of how trustworthy the
dataset is, organised by the **DAMA-DMBOK data-quality dimensions** (the data profession's
standard categories for "what does good data mean?").

It is *not* the raw output of the test run. When you run `dbt build`, dbt executes each test and
prints a machine-style pass/fail log. This scorecard **curates and interprets** that output: for
each quality dimension it states which test checked it, the result, the actual numbers, and — most
importantly — **what it means in plain English**. It's the artifact you would hand a data steward
or a stakeholder who asks *"can I trust this data, and where are its weak spots?"* without making
them read dbt logs.

Generated from the full-data `dbt build` on 2026-09-19 (**37 pass, 4 warnings, 0 errors**, 41 checks).

## Scope note (read this first)

- The **dbt tests run across the entire collected dataset** — all service days (Thursday tail,
  Friday, Saturday morning): `fct_stop_delays` = 54,665 rows, `fct_trip_punctuality` = 5,710 rows.
- The **analysis, however, uses only the Friday service day** (`fct_stop_delays` = 51,500 rows;
  `fct_trip_punctuality` = 3,957 trips) — see the article/methodology for why.
- So a couple of warnings below look alarming at the full-dataset level but are negligible within
  the Friday analysis set. Each row makes that distinction explicit.

---

## The scorecard

| DAMA dimension | The question it asks | Test | Result | Numbers | What it means |
|---|---|---|---|---|---|
| **Completeness** | Are required values present? | `not_null` on `trip_id`, `stop_id`, `service_date`, `station`, `stop_delay_key` | ✅ Pass | 0 nulls | Every key field is fully populated. No record is missing its identity or its station. |
| **Completeness (measure)** | Is the delay value present? | `not_null` on `arrival_delay_seconds` (warn-only) | ⚠️ Warn | 395 of 54,665 null (0.7%); 389 in Friday | These stops carry only a *departure* delay, not an arrival delay — legitimate for origin stops. Not a defect; flagged for transparency. |
| **Uniqueness** | Are there duplicates? | `unique` on `stop_delay_key` (`trip_id`+`stop_id`+`service_date`) and on `trip_instance_key` | ✅ Pass | 0 duplicates | Exactly one delay estimate per stop per service day, and one row per journey instance. **This test now guards the correct grain** — an earlier version keyed only on `trip_id`+`stop_id` passed while silently merging the same trip across two days (2,761 collisions). Fixed. |
| **Validity** | Are values from the allowed set? | `accepted_values` on `confidence` | ✅ Pass | 100% in {estimated_actual, prediction} | The confidence flag never holds an unexpected value. (For Friday specifically, **all 51,500 rows are `estimated_actual`** — the analysis set contains zero low-confidence predictions.) |
| **Referential integrity** | Do the links between tables hold? | `relationships`: realtime `trip_id` → static `trips` (warn-only) | ⚠️ Warn | 1.49M orphan rows overall; **Friday 1.7%** (66/3,957 trips), **Saturday 87.6%** (1,055/1,205) | The headline governance finding: the static bundle regenerates `trip_id`s daily and we downloaded it once, so it matches *its own* day. Friday (our analysis day) is 98.3% clean; Saturday is broken and is excluded. See §"Notable findings". |
| **Timeliness** | Is the data on-cadence? | `assert_snapshot_cadence` (gaps > 150s; warn-only) | ✅ Pass | 0 gaps across 2,160 snapshots | The poller ran the full 36 hours with **zero gaps and zero failed fetches** — the 60-second cadence held throughout, so no trips were lost to collection outages. |
| **Consistency** | Are values in a sane range? | `assert_delay_within_sane_range` (\|delay\| > 3h; warn-only) | ⚠️ Warn | 1 of 54,665 rows | One implausible feed prediction (~12.9 hours) was caught and flagged for review rather than silently trusted — the check earning its keep. |

*(One further warn: `scheduled_start` is null for 1,302 trip instances — the orphan trips with no
static-schedule match, i.e. the same static-versioning issue. Warn-only, and outside the Friday set.)*

---

## Notable findings

**1. Referential integrity → the static-versioning risk, proven.** The single most valuable thing
the scorecard surfaced. It is a *warn*, not an *error*, on purpose: some realtime-only trips
(`ADDED`, `REPLACEMENT`) legitimately won't be in a static schedule, so a hard failure would be
wrong. But the *magnitude* (87.6% of Saturday) revealed that the schedule bundle's `trip_id`s are
not stable across days — you must join realtime to the bundle in force on that service date. Scoping
to Friday keeps the analysis at 98.3% integrity; the finding is documented as a limitation and a
multi-day design requirement (see `governance_note.md`).

**2. A green test once hid a real bug.** The uniqueness test *passed* before we fixed the dedup
grain — because deduplication guarantees uniqueness by construction, so the test literally could not
see that two days' runs of one `trip_id` had been merged. The lesson, now baked into the models:
**test at the right grain, or a passing test proves nothing.**

**3. The analysis set is 100% high-confidence.** Because of the 24-hour-inside-36-hour window, every
one of the 51,500 Friday stop-delay records is `estimated_actual` — none are low-confidence
predictions. The quality of the *analysed* data is as high as this feed allows.

## Overall verdict

For the **Friday analysis set**, quality is strong: complete keys, correct-grain uniqueness, valid
confidence values, full-cadence timeliness, and 100% high-confidence delay readings. The two
substantive warnings (referential integrity, one consistency outlier) are understood, quantified,
and either designed-around (Friday scope) or flagged for review (the 12.9h outlier) — not swept
aside. The dataset is fit for the delay analysis it was built for, with its limits documented.
