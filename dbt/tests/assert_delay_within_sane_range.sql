-- DAMA-DMBOK dimension: CONSISTENCY.
-- An arrival delay outside +/- 3 hours almost certainly indicates a unit or sign
-- error (delays are in seconds; 3h = 10,800s is already an extreme real-world delay).
-- Warn-only: the raw feed occasionally emits an implausible prediction (e.g. a
-- 12.9h "delay" was observed on a low-confidence row). We surface these for review
-- in the quality scorecard rather than hard-failing the pipeline on feed noise.
-- A "clean" run returns zero rows.
{{ config(severity='warn') }}

select
    stop_delay_key,
    arrival_delay_seconds
from {{ ref('fct_stop_delays') }}
where arrival_delay_seconds is not null
  and abs(arrival_delay_seconds) > 3 * 60 * 60
