# Article draft — TfNSW train-delays governance project

> **STATUS: DRAFT SKELETON.** Data-independent sections (1–4, 7, 8) are drafted in near-final
> prose. Section 5 (governance) is mostly written — only the scorecard numbers are pending.
> Section 6 (findings) is scaffolded and must be filled **after the full-day data lands and the
> mart is rebuilt**. Port this into `personal_portfolio_website/src/content/articles/` as an
> `.mdx` file at publish time; hosting + copy-script notes are at the bottom.
>
> Markers used below: **[FILL AFTER DATA]**, **[SCORECARD]**, **[CHART]**, **[SVG]**.

---

## Frontmatter (for the eventual .mdx)

```yaml
---
title: "Governing a real dataset: train delays, dbt, and DAMA-DMBOK"   # working title — see alternatives at foot
summary: "I applied a data-governance framework hands-on to a real Transport for NSW feed — quality tests, a privacy assessment, and lineage — and wrote it up so a beginner can follow every step."
date: 2026-09-XX          # set at publish
tags: ["data engineering", "data governance", "dbt", "data quality", "privacy", "DAMA-DMBOK", "duckdb", "learning in public"]
draft: true               # flip to false at publish
---
```

**[SVG]** Hero image (match the `ThemedSvg` pattern of the skill-demand article): a simple
inputs → processes → outputs pipeline diagram, subtitled *"Turning a live train feed into
governed, analysis-ready data — in a day."*

---

## Hook (opening, no heading)

The job I most want asks for the one thing my résumé can't yet prove. It is a Senior Data
Engineer role centred on **data governance** — DAMA-DMBOK, privacy regulation, data quality as
a discipline in its own right. I have done years of the *engineering* that governance sits on
top of, but never under a governance title. My own cover letter admits it: my governance
experience "has come through the engineering lens rather than a dedicated governance title."

So I spent a day closing that gap the only honest way I know — by doing it. I took a live,
public Transport for NSW train feed and built a small but complete governed pipeline on top of
it: real collection, real transformations, real quality tests mapped to a real framework, a
real privacy assessment, and living documentation. This post is two things at once: a walk
through **how that system works**, written so a beginner data engineer can follow every step,
and an honest account of **what one day of data can and cannot tell you**.

- [Why I built this](#why-i-built-this)
- [The system at a glance](#the-system-at-a-glance)
- [Inputs: collecting a live feed, and the decisions behind it](#inputs-collecting-a-live-feed)
- [Understanding the data: what a "trip" really is](#understanding-the-data)
- [Processes: the dbt pipeline, explained for beginners](#processes-the-dbt-pipeline)
- [The governance layer](#the-governance-layer)
- [Outputs: what a day of Sydney train delays shows](#outputs-what-a-day-shows)
- [Scope, limits, and what more could be done](#scope-limits-and-what-more)
- [What I learned](#what-i-learned)

---

## Why I built this

Two motivations, and I'll be straight about both.

The first is targeted. A specific role I care about lists data governance as its core, and names
gaps I genuinely have: DAMA-DMBOK applied hands-on rather than read about; privacy regulation
(the Australian Privacy Principles, GDPR) applied to real data; governance as a dedicated
practice, not a by-product of building pipelines. You cannot fake those in an interview. You can
demonstrate them — even at small scale — by doing them once, carefully, and showing your work.

The second is broader, and it's why this doubles as a piece for *any* data role. In a separate
analysis I ran on the data-job market, the fastest-rising skills for Data Engineers between 2021
and 2026 were **dbt, CI/CD, and data governance** — dbt went from 2% to 21% of ads; governance
roughly quadrupled. This project happens to sit right on top of that finding. It is a working
example of the skills the market is moving toward, built on a stack anyone can run locally.

A note on framing that runs through the whole post: I am not claiming governance seniority. I am
showing what happens when someone with a strong engineering background applies a governance
framework to a real dataset for the first time. That honesty is deliberate — it is more credible
than overclaiming, and it turns out that *reaching a defensible conclusion and documenting your
reasoning* is itself the governance skill.

---

## The system at a glance

Before the detail, here is the whole system as inputs → processes → outputs — the way any data
engineer would first sketch it.

**[SVG]** Replace this ASCII sketch with a proper diagram at publish:

```
INPUTS                     PROCESSES                              OUTPUTS
──────                     ─────────                              ───────
TfNSW GTFS static  ─┐
(schedule, ZIP)     │      poller (poll_rt.py, 60s)   ┐
                    ├────▶  writes each snapshot ──────┤
TfNSW GTFS-Realtime │      to DuckDB immediately       │
(trip updates,      ┘                                  ▼
 protobuf, every                    dbt: staging → intermediate → mart
 10s)                               + 23 data-quality tests
                                    + classification metadata
                                                       │
                                                       ├──▶ fct_stop_delays (analysis-ready table)
                                                       ├──▶ data-quality scorecard
                                                       ├──▶ PIA-lite classification
                                                       └──▶ dbt docs (lineage + data dictionary, hosted)
```

The stack is deliberately humble: **Python + DuckDB + dbt**, all local. Nothing here needs a
cloud data platform, and that's a point I return to in the limits section — the governance
*thinking* is the same whether the engine underneath is a laptop or a warehouse.

Everything in this post maps onto one of those three columns. Collection is the input. The dbt
pipeline and its tests are the process. The mart, the scorecard, the privacy assessment, and the
docs are the outputs.

---

## Inputs: collecting a live feed, and the decisions behind it {#inputs-collecting-a-live-feed}

Transport for NSW publishes two feeds for Sydney Trains: a **static** schedule (a daily ZIP of
what's *meant* to happen) and a **realtime** feed of trip updates (what's *actually* happening,
as delay predictions, refreshed every ten seconds). The interesting data — delays — lives in the
realtime feed, and it has one behaviour that shaped every collection decision:

> **A stop disappears from the feed once a train passes it.** Miss the window and that stop's
> delay is gone for good — it is not recoverable from a later snapshot.

That single fact drives the design:

- **Poll every 60 seconds.** The shortest gap between consecutive stops on a trip is about two
  minutes, so a 60-second cadence guarantees every stop is seen at least once before it drops.
  Slower risks missing stops; faster (the feed only refreshes every 10s) just makes near-
  duplicate rows for no gain.
- **Write every snapshot to disk immediately.** The collector (`poll_rt.py`) inserts each
  snapshot into DuckDB and checkpoints it before sleeping. A crash at hour 20 keeps hours 1–20 —
  nothing is buffered in memory across the run.
- **Log the gaps.** If a fetch fails or runs long, it's logged. Missing data you can *see* is a
  managed limitation; missing data you can't see is a silent lie. (This later becomes a quality
  test — see Timeliness, below.)
- **Run one continuous weekday, and stop it in the small hours.** I collected roughly 24–26
  hours across a single weekday, then stopped in the overnight lull (~02:00–04:00). The reason is
  subtle and worth the paragraph below.

**The collection-boundary effect.** Because a delay is only ever a *prediction* until the train
passes, the closest thing to an "actual" delay is the *last* value seen before a stop dropped
from the feed. But any trip still running when you stop the collector never gets that final
reading — its later stops stay predictions. Stop mid-peak and you strand an entire evening's
worth of trips as low-confidence data. Stop in the overnight lull and only a handful of trips are
affected. This isn't a bug to fix; it's a real property of the data to **design around and then
document** — which is exactly the kind of judgement governance is about.

By the end of the run the raw table held **8,262,921 rows** across **2,159 snapshots**, spanning
Friday 00:10 to Saturday 12:10. *(The analysis uses only a clean 24-hour slice of that — see the
next section.)*

---

## Understanding the data: what a "trip" really is {#understanding-the-data}

*This section is for anyone who wants to replicate this with the TfNSW feed. A few things about
the data are non-obvious and will bite you if you don't know them.*

### A `trip_id` is not a unique journey

The natural assumption is that `trip_id` uniquely identifies one train journey. It does not. A
`trip_id` like "the 07:15 Central→Hornsby" is **reused every day that service runs.** In our own
36-hour collection, **518 `trip_id`s appeared on both Friday and Saturday**, and **2,761
`(trip_id, stop_id)` combinations were seen on more than one day.** So to identify a single, real
*instance* of a journey you need a **composite key: `trip_id` + the service date it ran.**

This isn't academic — it exposed a real bug in our first pipeline. Our deduplication step keeps,
for each `(trip_id, stop_id)`, the *latest* reading. Run it over two days and it silently merges
Friday's and Saturday's runs of the same service into one, keeping only the later. Worse, our
`unique` test on `(trip_id, stop_id)` **passed anyway** — because deduplication *guarantees*
uniqueness on that key by construction, so the test literally could not detect the problem. **The
lesson: a green quality test is not proof of correctness — you have to test at the right grain.**
The fix is to key everything on `trip_id + stop_id + service_date`.

### The service day: why timetable times run past `24:00:00`

A "day of service" in transit does not run midnight-to-midnight. It runs from one quiet point in
the small hours to the next (conventionally ~3am), so that late-night trains stay grouped with the
day they belong to. A train departing **Friday 11:50pm** and arriving **Saturday 12:40am** is part
of **Friday's** service — and the timetable writes that arrival as `24:40:00`, not `00:40:00`, to
say "still Friday's service day, just past midnight." That's why arrival/departure times in the
static schedule can exceed 24 hours, and why you must never load them as a normal clock time.

So a **service date** answers *"which day's timetable does this run belong to?"* — not *"what's
today's calendar date?"*

### A governance footnote: the empty `start_date`

The realtime feed *has* a field for exactly this — `start_date`, meant to carry each trip's service
date. **Transport for NSW leaves it empty** — it's an optional field in the GTFS-Realtime
specification, and it is blank in **100% of all 8.26 million rows** we collected. Our extraction is
the standard one; this is an upstream choice, not a collection error. It's a small but real
**data-completeness gap in the source**, and the governed response is to (a) record it as a known
source limitation and (b) **derive the service date ourselves** from the observation timestamps —
which is what we do, so downstream models never depend on a field the provider doesn't populate.

### Three different "start" times

Once you have a service date, a single journey actually has three distinct start timestamps, and
keeping them separate matters:

1. **Scheduled start** — from the static timetable: the scheduled departure from the origin stop.
   *When it was meant to leave.*
2. **Actual start** — scheduled start plus the observed departure delay at the origin. *When it
   actually left.* Measurable for ~86% of trips here (the feed doesn't always report the origin).
3. **Feed-appearance time** — the first snapshot in which the trip appeared. This is a *collection
   artifact* (when the operator published it), not a real event — useful only for validating how
   far ahead of departure trips enter the feed. **[VERIFY — report the measured lead-time
   distribution after rebuild.]**

Scheduled-vs-actual is a real punctuality signal; feed-appearance is methodology. Conflating them
(as it's tempting to do) would quietly turn a data-pipeline quirk into a fake finding.

### One fixed day here; a rolling window in practice

For this article we analyse a **single fixed 24-hour window** (trips running from ~1am Friday to
~1am Saturday) — a deliberate, simple scope for a one-day piece. But note the honest limitation:
**a fixed cutoff arbitrarily truncates any trip straddling the boundary.** A production system
doing ongoing multi-day analytics would instead use a **rolling window** keyed on `service_date`,
so no journey is ever cut in half by an arbitrary edge. The composite-key and derived-service-date
work above is precisely what makes that future rolling approach possible without re-architecting.

---

## Processes: the dbt pipeline, explained for beginners {#processes-the-dbt-pipeline}

The raw data is genuinely hard to use: stops are codes (`2000322`, not "Central Station"), delays
are in seconds, schedule times look like `25:10:00` (that means 1:10am the *next* day), and the
same train-at-a-stop appears in hundreds of snapshots. Getting from that mess to a clean,
trustworthy table is the job of **dbt**.

### The one idea behind dbt

You don't write instructions to build tables. You write a `SELECT` query describing the *result*
you want, save it as a small file (a **model**), and dbt handles the rest — creating the tables,
running them in the right order, testing them, and documenting them. Think of dbt as a head chef:
you write the recipes, and the chef works out what to cook first, cooks it, and tastes each dish.

### Three layers

The pipeline is organised in three layers, each with one job:

1. **Staging** — one model per raw table, doing nothing but cleaning *that* table: rename columns,
   fix types, handle the gotchas (the `25:10:00` overflow, the empty-string quirks, the always-
   null `stop_sequence`). Wash and chop the ingredients.
2. **Intermediate** — the hard reshaping. Here, `int_rt__latest_update` collapses those hundreds
   of snapshots down to the *last sighting* of each train-at-a-stop, and stamps each one
   `estimated_actual` (the train had passed — a trustworthy reading) or `prediction` (still
   forecast at cutoff). Cook the components.
3. **Mart** — the readable result. `fct_stop_delays` joins the deduplicated delays to real station
   and line names, delay in minutes. This is the table you'd point a dashboard at. Plate the dish.

### How dbt knows the order

Inside a model, you never hard-code another table's name — you write `{{ ref('other_model') }}`.
That does two things: it tells dbt "this depends on that" (so dbt computes the run order itself),
and at run time it's swapped for the real table name. From every `ref()` across the project, dbt
assembles a **DAG** — a dependency graph — and runs independent models in parallel, dependent
ones in sequence. You can see that exact graph in the hosted docs (linked below).

### Fresh vs fast: views and tables

The same query can be stored two ways. A **view** saves only the query and re-runs it live on
every read (always fresh, no storage). A **table** runs the query once and stores the rows (fast
to read, but frozen until you rebuild). Staging and intermediate are views (light, always current
with the still-growing raw data); the mart is a table (the stable artifact you query often). The
practical catch, and a genuine gotcha worth stating: **a table shows nothing new until you re-run
dbt** — which is why the final mart is rebuilt once collection ends.

**→ Explore the live pipeline yourself:** the full lineage graph and data dictionary are hosted at
**[LINK: /train-delays-dbt-docs/]** (regenerated against the full dataset).

---

## The governance layer {#the-governance-layer}

Everything above is data *engineering* — moving and shaping data. Governance is the layer that
makes the result **trustworthy, understandable, safe, and accountable**. This is the part the
role is really about, and it's four things.

### 1. Data quality, mapped to DAMA-DMBOK

DAMA-DMBOK is the data profession's standard framework, and its data-quality area defines
standard **dimensions** — agreed categories for what "good data" means. I didn't just scatter
checks around; I mapped each dbt test to a dimension, so the tests *implement a recognised
framework* rather than being ad-hoc:

| DAMA dimension | The question it asks | The test |
|---|---|---|
| Completeness | Is anything missing? | `not_null` on `trip_id`, `stop_id` |
| Uniqueness | Any duplicates? | `unique` on the trip+stop key |
| Validity | Are values in the allowed set? | `accepted_values` on `confidence` |
| Referential integrity | Do the table links hold? | `relationships`: realtime `trip_id` → static `trips` |
| Timeliness | Is the data on-cadence? | custom test flagging polling gaps > 150s |
| Consistency | Are values sane? | custom test flagging delays beyond ±3h |

A test in dbt hunts for *bad* rows and passes when it finds none. On the first run against a
partial slice, 28 passed and 2 warned — and one warning was the framework earning its keep: the
consistency test caught a feed prediction of nearly 13 hours, an implausible value flagged for
review rather than silently trusted.

The **data-quality scorecard** turns those test results into a one-page, plain-English report — for
each dimension: the test, the result, the numbers, and what it means (full version in
`docs/quality_scorecard.md`). On the full-data build: **37 checks passed, 4 warned, 0 failed.** The
passes cover completeness (all keys populated), uniqueness (one delay per stop per service day — at
the *correct* grain, see below), validity (the confidence flag is always legal), and timeliness
(**zero gaps across all 2,160 snapshots** — the 60-second cadence never broke). The warnings are the
interesting part.

**What "referential integrity" caught, in plain terms.** A realtime update identifies its train only
by a `trip_id`; to attach real station names and a schedule we **join that id to the static
timetable**. An **orphan** is a realtime `trip_id` with *no match* in the timetable we downloaded —
an update we can't tie to any scheduled service. On **Friday just 1.7% of trips were orphans (98.3%
matched); on Saturday, 87.6% were orphans.** The cause isn't corruption — it's **versioning**: TfNSW
republishes the timetable every night and re-mints its `trip_id`s, and we downloaded it once (on
Friday). By Saturday the realtime feed was quoting a *newer* timetable's ids that our single copy
didn't contain. Scoping the analysis to Friday keeps integrity at 98.3%; the lesson — *you must join
realtime to the timetable version that was live at the time* — is the project's clearest governance
takeaway.

**A green test that had been lying.** The uniqueness test *passed* even while an earlier version of
the pipeline was silently merging the same `trip_id` across two days — because deduplication makes a
key unique *by construction*, so the test couldn't see the collision. Fixing the key to
`trip_id + stop_id + service_date` fixed the model; the lesson is that **a passing test proves
nothing unless it checks the right grain.**

### 2. Privacy — a mini Privacy Impact Assessment

The first step of any Privacy Impact Assessment is a **threshold assessment**: does this data
even contain personal information? I worked through every table against the actual legal
definition — the Australian Privacy Act's test for *personal information* (about an identified or
reasonably identifiable individual), cross-checked against GDPR's equivalent — and concluded, with
reasons, that it is all **public**, with no personal information present.

The interesting part was the borderline fields, because governance is about the judgement, not
the label. A `vehicle_id` could in principle identify a *driver* — but only if joined to crew
rosters (the "mosaic effect", where harmless data becomes personal in combination), and the field
is empty in the feed anyway. Accessibility flags describe *stations*, not people. Crowding data is
aggregate, never individual. I recorded what *would* change the assessment — joining to Opal
ticketing, CCTV, or rosters — so the conclusion is operational, not just a stamp.

Concluding "no personal information here, and here is exactly why" is not a workaround for lacking
a personal-data example. It *is* the privacy-governance skill.

### 3. Metadata and lineage

Data nobody understands can't be governed. Each model and column carries a plain-English
description and a `classification` tag, written next to the SQL. Because that metadata lives in
the code — and the lineage is derived from the `ref()` graph — `dbt docs` generates a
**self-documenting, always-in-sync** data dictionary and an interactive lineage graph. That's the
same discipline enterprise catalogue tools provide, at small scale. It also answers the questions
governance actually needs: *what breaks if this source is wrong* (trace downstream) and *where did
this number come from* (trace upstream).

### 4. Ownership, retention, and known risks

A short policy note records the human layer: who the **data steward** is, how **change management**
works (the static bundle has no version number, so silent daily drift is an accepted, documented
risk — with the production fix, daily diffing, stated), and a register of **known limitations**
reframed as acknowledged risk rather than buried caveats.

---

## Outputs: what a day of Sydney train delays shows {#outputs-what-a-day-shows}

All figures below are for the **Friday service day**, using **estimated-actual** readings only —
51,111 stop records across 3,656 trips and 321 stations. Read them as *"what happened on this one
weekday,"* not a verdict on the network in general.

**The headline: it was a good day for the network.** The median arrival delay was **0.0 minutes**,
**97.5%** of stops were within five minutes of schedule, and only **2.5%** ran more than five minutes
late. Trains also *left* their origin essentially on time (median origin-departure delay 0.0 min).
**[CHART]** delay distribution.

**Delay accumulates as a journey goes on.** Trains start on time but slowly lose it: average delay
roughly **doubles** from the start of a trip to the end — about 0.4 min in the first tenth of a
journey, rising to ~1.0 min in the final tenth. The amounts are small, but the build-up is clear and
monotonic: the further along a train is, the more time it has shed. **[CHART]** average delay by
position through the trip.

**The surprise: midday, not rush hour, was worst.** Conventional wisdom says the peaks are the
problem. Not this Friday. The **morning peak (7–9am) was the *best* window** (avg 0.38 min, 1.5% of
stops >5 min late), and the evening peak (4–7pm) nearly matched it (0.56 min, 1.4%). The worst window
was the **middle of the day (10am–3pm)**: avg 0.95 min and 4.3% of stops >5 min late, peaking around
noon (7.8% late). An average-delay metric and a percentage-late metric agree, so it isn't a single
outlier. **[CHART]** delay by hour of day. *(I won't over-claim the cause — off-peak track work and
thinner recovery capacity are plausible — but the pattern is real and worth surfacing.)*

**Even the "worst" lines and stations were barely late.** The lines with the most lateness were
**SHL** and **T7** (SHL: 7.3% of stops >5 min late, median 0.92 min); every suburban **T-line had a
median of zero**. The most-delayed stations — **Cronulla** and **Jannali**, both on the Cronulla
branch — still had medians under half a minute. On this day, no corner of the network was performing
badly. **[CHART/TABLE]** worst lines.

**A methodology aside that became a finding.** Trips appear in the realtime feed a **median of 24.5
minutes** before their scheduled departure — but with a wide spread (10th percentile 1.5 min, 90th
~2.5 hours), and 133 trips appeared *after* their scheduled time. This is exactly why we defined
"actual start" from the origin *departure delay* rather than from when a trip first appears: the
feed's appearance time is far too loose to stand in for a real departure. **[CHART]** feed lead-time
distribution.

---

## Scope, limits, and what more could be done {#scope-limits-and-what-more}

This is a one-day proof, and being clear about its edges is part of the point — an interviewer
(and a reader) should trust the boundaries as much as the results.

- **One weekday only.** No weekend, so no weekday-vs-weekend comparison. A documented next step,
  not a finding.
- **Estimates, not actuals.** Every delay is the last prediction before a stop dropped from the
  feed; values can wobble up to ~70s near arrival. The `confidence` column is honest about which
  readings are trustworthy.
- **A public, non-personal dataset.** The privacy work concluded "no PII" — which is genuine
  governance, but it means this project does not demonstrate handling *actual* sensitive data.
- **A local stack, on purpose.** Databricks, Unity Catalogue, and Fivetran are deliberately *not*
  here. Databricks I already use in production elsewhere; Unity Catalogue and Fivetran are real
  gaps I chose to defer rather than half-learn in a day. The governance reasoning transfers to any
  of them.
- **Docs are regenerated by hand, not CI/CD.** In production you'd auto-generate and host the
  documentation on every merge, with freshness timestamps. Here it's a manual regenerate-and-copy.
- **Cascading (knock-on) delays are largely invisible here.** The main channel — a late train
  delaying the *next* service that reuses its physical train or crew — can't be traced, because the
  feed's `vehicle_id` is empty in 100% of rows (another upstream completeness gap, echoing the empty
  `start_date`). What we *can* see bounds it: 91.5% of trains still departed their origin within a
  minute, so on this low-delay day little cascading reached departures. Consecutive trains at the
  same platform do show a moderate delay correlation (~0.29, rising to ~0.31 at tight headways) —
  consistent with *some* propagation, but equally explainable by shared causes (e.g. the midday
  slowdown), so not proof. Studying knock-on properly would need a populated `vehicle_id`, a
  disruption day, or track topology — a documented future extension.

### Would this methodology survive multi-day analysis?

Worth asking of any pipeline: does it scale beyond today's one-day run to weeks or months? Here the
answer splits cleanly, and knowing *which* half is which is the point:

- **The data modelling is ready.** Trip identity (`trip_id + service_date`), the derived service day,
  the dedup grain, and the marts were all built per-instance, and the 24-hour scope is a *filter*,
  not something baked into the models — so a rolling multi-day window needs no re-work.
- **Two things must change first.** (1) **Static ingestion** — we download the timetable once, but
  its `trip_id`s change nightly (that's the 87.6%-Saturday finding), so a real pipeline must archive
  and version the timetable *per day* and join each day to its own. (2) **The confidence rule** —
  `estimated_actual` vs `prediction` is decided against the end of *this one batch*, which is
  meaningless for a never-ending pipeline; it would need a rolling definition. Add incremental loads
  instead of full rebuilds, and it scales.

The honest one-liner: *the modelling is multi-day-ready by design; the ingestion and confidence
logic are deliberate single-run simplifications.*

What more could be done, given more than a day: multi-week collection, weekday-vs-weekend and
seasonal comparisons, the same governance layer on a cloud platform with a real catalogue, and an
automated freshness/CI pipeline. This is a taste of the method, not the finished meal.

---

## What I learned {#what-i-learned}

**[FILL / POLISH AT PUBLISH — reflective close.]** Draft themes to land:

- Governance is less about tools than about *judgement made visible* — the reasoning in the
  privacy note and the risk register was harder, and more valuable, than the SQL.
- Mapping tests to a named framework changed how they read: "I added some checks" became "I
  implemented DAMA's quality dimensions."
- The honest framing (a first hands-on application; a one-day taste) was a feature, not an
  apology — and it's the version of myself I'd want an employer to meet.
- Link to the repo; invite other beginners to clone it and follow the same path.

---

## Working title alternatives

1. *Governing a real dataset: train delays, dbt, and DAMA-DMBOK* (current)
2. *What one day of Sydney train data taught me about data governance*
3. *I applied a data-governance framework to a live train feed. Here's every step.*
4. *From raw feed to governed data: a beginner's walk through dbt and DAMA-DMBOK*

---

## Publish checklist (hosting + port)

- [ ] Rebuild dbt on the full dataset (`dbt build`) and confirm 0 errors.
- [ ] Fill Section 6 findings + charts; fill Section 5 scorecard; fill Section 3/collection totals.
- [ ] `dbt docs generate` against full data.
- [ ] Copy docs into portfolio: `personal_portfolio_website/public/train-delays-dbt-docs/`
      (mirror the existing `public/skill-graph/` pattern — ideally a small copy-script under
      `scripts/`, so regeneration isn't a manual drag). Served at `/train-delays-dbt-docs/`.
- [ ] Note in the article that public hosting is *licensed by* the PIA-lite (data is public, no PII).
- [ ] Create the hero + diagram SVGs (`ThemedSvg`, matching the skill-demand article).
- [ ] Port this file to `src/content/articles/tfnsw-train-delays-governance.mdx`, convert tables/
      figures to the site's components, set `date`, flip `draft: false`.
- [ ] Cross-link the skill-demand article (the governance/dbt/CI-CD rising-skills connection).
