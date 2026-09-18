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

By the end of the run the raw table held **[FILL AFTER DATA: ~N million]** rows across
**[FILL AFTER DATA: N]** snapshots.

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

**[SCORECARD]** Final data-quality scorecard against the full dataset — one row per dimension:
test, result, pass rate, and what it means. Build from `dbt build` results after the full run.

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

> **[FILL AFTER DATA]** This section is deliberately empty until the full weekday is collected and
> the mart is rebuilt. Answer these questions from `fct_stop_delays` (estimated_actual rows only,
> and state that constraint), each with a chart and an honest confidence caveat:

- **Which lines and stations had the worst on-time performance?** **[CHART]** bar chart, top N.
- **Do delays accumulate as a trip progresses?** **[CHART]** delay vs stop-sequence.
- **Was the morning peak worse than the evening peak?** **[CHART]** delay by hour-of-day.
- Headline numbers: median delay, % of stops within 5 min, worst single corridor. **[FILL AFTER DATA]**

Frame every finding as *"for this one weekday, using estimated-actual readings"* — not as a
general claim about the network.

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
