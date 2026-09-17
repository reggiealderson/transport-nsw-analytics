# Data classification & privacy threshold assessment (PIA-lite)

**Dataset:** TfNSW Sydney Trains GTFS (static schedule) + GTFS-Realtime (trip updates)
**Assessed:** 2026-09-18 · **Assessor:** Reggie Alderson
**Outcome:** All tables classified **`public`**. No personal information present. The
Australian Privacy Principles (APPs) are **not engaged** by this dataset.

---

## 1. What this document is (and how honest it is)

This is a **threshold privacy assessment** — the first step any Privacy Impact
Assessment (PIA) begins with: *does this data actually contain personal information,
and if so, whose and what kind?* If the answer is "none", the assessment records that
conclusion **with reasoning**, and the downstream PIA obligations (data-flow mapping,
risk rating, mitigations) fall away.

I'll be upfront about the framing, because it matters for how to read this: I had
studied the APPs and DAMA-DMBOK's data-governance material for a role application, and
this is me applying that threshold test *hands-on to a real dataset for the first
time*, rather than claiming years of privacy-officer practice. The point of including
it is that **reaching a defensible "no personal information here, and here is exactly
why" is itself the governance skill** — not a workaround for lacking a personal-data
example. A careful assessment that concludes *public* is a real deliverable; waving the
dataset through with "it's just train data" is not.

---

## 2. The test being applied

**Privacy Act 1988 (Cth), s 6(1) — personal information:**
> "information or an opinion about an identified individual, or an individual who is
> **reasonably identifiable**, whether the information or opinion is true or not, and
> whether recorded in a material form or not."

Two limbs matter here:

1. **Is the information *about an individual*?** (as opposed to about a vehicle, a
   station, a route, or an aggregate service pattern)
2. **Is an individual *reasonably identifiable*** from it — alone, or in combination
   with other information reasonably at hand? (the "mosaic" / re-identification limb)

**Sensitive information** (s 6(1)) is a protected subset — health, racial or ethnic
origin, political/religious/philosophical beliefs, sexual orientation, criminal record,
biometric and genetic data. It attracts stricter handling under APP 3. I check for it
explicitly below because two columns (`wheelchair_boarding`, `wheelchair_accessible`)
superficially look health-adjacent.

**GDPR cross-check (Art 4(1))** — because the role also references GDPR — uses an
equivalent test: *"any information relating to an identified or identifiable natural
person."* The conclusion is the same under both regimes, so this document reasons
primarily under the APPs and notes GDPR only where it would differ (it doesn't here).

---

## 3. Table-by-table assessment

Each table is judged against the two limbs in §2. "Personal info?" = does it contain
information about a reasonably identifiable individual.

### Static schedule (`raw_gtfs`)

| Table | Contents | Personal info? | Reasoning |
|---|---|---|---|
| `agency` | 2 operators (Sydney Trains, NSW TrainLink), incl. `agency_phone` | **No** | Information about *organisations*, not individuals. `agency_phone` is a published general business line for the operator, not a named person's contact. Organisational contact details are not personal information. |
| `routes` | Train lines (T1, T2…), colours, types | **No** | Attributes of network infrastructure/services. No individual. |
| `calendar` | Which service patterns run on which weekdays; validity dates | **No** | Timetable metadata. No individual. |
| `stops` | 1,214 stations/platforms: name, `stop_lat`/`stop_lon`, `wheelchair_boarding` | **No** | Geographic and facility attributes of **public infrastructure**. Coordinates locate *stations*, not people. `wheelchair_boarding` describes whether a *stop* is step-free — an accessibility property of the facility, **not** any individual's disability, so it is not sensitive information either. |
| `trips` | 65,947 scheduled journeys: `trip_id`, `trip_headsign`, `direction_id`, `wheelchair_accessible`, `vehicle_category_id` | **No** | Describes scheduled *services* and *rolling stock*. `wheelchair_accessible` is a property of the vehicle/service, not a passenger. No individual. |
| `stop_times` | 1.2M scheduled arrival/departure events | **No** | "Service X is scheduled at stop Y at time Z." No individual. |
| `occupancies` | Typical crowding level per trip/stop by day-of-week (`occupancy_status`) | **No** | **Aggregate** expected-crowding indicator (a level code), derived from counts — never per-passenger. No individual is identifiable from an aggregate "how full is this service usually" figure. |
| `vehicle_boardings` | Boarding-area layout per carriage type | **No** | Physical configuration of train carriages. No individual. |
| `vehicle_couplings` | How carriages couple into consists | **No** | Rolling-stock engineering data. No individual. |
| `vehicle_categories` | Carriage-type lookup | **No** | Reference data. No individual. |

### Realtime feed (`raw_rt`)

| Table | Contents | Personal info? | Reasoning |
|---|---|---|---|
| `trip_updates` | Per-snapshot delay predictions per trip/stop; `trip_id`, `stop_id`, `route_id`, `arrival_delay`, `vehicle_id`, schedule relationships | **No** | State of the *service network* at an instant. Delays attach to trips and stops, not people. See the `vehicle_id` note in §4. |

### dbt models (derived)

| Model | Personal info? | Reasoning |
|---|---|---|
| `stg_gtfs__*`, `stg_rt__trip_updates` | **No** | Type-cast / cleaned views of the sources above; introduce no new fields about individuals. |
| `int_rt__latest_update` | **No** | Deduplicated delay per trip+stop with a confidence label. Still service-level. |
| `fct_stop_delays` | **No** | Final mart: estimated arrival delay per trip+stop with station and line. The most person-adjacent question it can answer is "which *station* is most delayed" — about places and services, never passengers. |

---

## 4. The one field that deserved a second look: `vehicle_id`

A vehicle identifier is the closest thing in this dataset to something that *could*
become personal information — not directly (a train is not a person), but via the
**mosaic effect**: if `vehicle_id` were joined to a crew-rostering system, it might
reveal which driver worked a given run, making a *worker* reasonably identifiable.

Two things close this off:

1. **The field is empty.** In the collected data, `vehicle_id` is blank in **100%** of
   rows (0 distinct populated values out of 43,405 checked). TfNSW does not publish it
   on this feed, so there is nothing to link.
2. **The linking dataset is not reasonably available.** Crew rosters are internal to
   TfNSW and not accessible to a public consumer of this feed. Under the "reasonably
   identifiable" limb, a re-identification path that requires data one cannot lawfully
   or practically obtain does not, on its own, make the public data personal.

**Recorded as a watch-item:** if a future feed version populated `vehicle_id`, the
mosaic risk should be re-assessed by whoever *does* hold rostering data (i.e. TfNSW
internally) — for an external analyst it remains non-personal.

---

## 5. Conclusion

- **Classification: `public`** for every source table and every derived model.
- **No personal information** (Privacy Act s 6(1)) and **no sensitive information**
  (s 6(1) subset) is present. The `wheelchair_*` fields describe facilities/vehicles,
  not people, and are therefore not health information.
- **The APPs are not engaged** by this dataset as held here; no collection notice
  (APP 5), use/disclosure (APP 6), or security (APP 11) obligations are triggered *by
  the data's content*. (Good engineering hygiene — e.g. not committing the API key —
  still applies, but that is security practice, not a Privacy Act obligation over
  personal information.)
- The conclusion is identical under **GDPR Art 4(1)**: no data relating to an
  identified or identifiable natural person, so no "personal data" and no data-subject
  obligations.

### What would change this assessment
This dataset is public *because of what it is*. The classification would need to be
redone the moment it were joined to any of:

- **Opal / ticketing / tap-on-tap-off data** → individual journey histories (personal,
  likely re-identifiable, and location-sensitive);
- **CCTV, Wi-Fi, or Bluetooth passenger-counting** → individuals in a place at a time;
- **Crew rostering** (via a populated `vehicle_id`) → identifiable workers.

Any of those would move the combined dataset from `public` to at least `internal` /
`restricted`, trigger the full APP set, and warrant a complete PIA rather than this
threshold note.

---

## 6. How this maps to a production governance process

This threshold assessment is deliberately lightweight because the answer is clean. In a
team setting it would be the front page of a fuller record that also carries:

- **Classification recorded in metadata, not just prose** — each source and model in
  this project is tagged `meta: {classification: public}` in its dbt `schema.yml`, so
  the label travels with the data and surfaces in `dbt docs` (see `docs/` and the
  lineage graph). Classification-as-prose rots; classification-as-metadata is queryable.
- **A named data steward** accountable for re-assessing on schema change (see the
  governance note, `docs/governance_note.md`).
- **A trigger to re-run this assessment** whenever a new source is introduced or two
  datasets are joined — the §5 "what would change this" list, operationalised as a
  checklist gate in the pipeline's change process.
