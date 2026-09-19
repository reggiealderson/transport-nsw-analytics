"""
Generate theme-aware SVG charts for the "One Delayed Friday" article, matching the
house style of the existing skill-demand article (inline <style>, muted grays, the
#1c7ed6 blue series, and a prefers-color-scheme dark override that the site's
ThemedSvg component rewires to the manual theme toggle).

Output: charts/*.svg  (later copied to personal_portfolio_website/public/images/articles/train-delays/)

Run:  .venv/bin/python make_charts.py
"""
import os
import duckdb

OUT = "charts"
os.makedirs(OUT, exist_ok=True)
FRI = "service_date = DATE '2026-09-18' AND arrival_delay_seconds IS NOT NULL AND abs(arrival_delay_seconds) <= 3*3600"

# Official Transport for NSW line colours (Open Data Hub, via Wikipedia).
LINE_COLORS = {
    "T1": "#F99D1C", "T2": "#0098CD", "T3": "#F37021", "T4": "#005AA3", "T5": "#C4258F",
    "T6": "#7C3E21", "T7": "#6F818E", "T8": "#00954C", "T9": "#D11F2F",
    "BMT": "#F99D1C", "CCN": "#D11F2F", "SCO": "#005AA3", "SHL": "#00954C", "HUN": "#833134",
}
DEFAULT_LINE = "#8792a0"

# Current official line names (Wikipedia / Transport for NSW).
LINE_NAMES = {
    "T1": "North Shore & Western Line", "T2": "Leppington & Inner West Line",
    "T3": "Liverpool & Inner West Line", "T4": "Eastern Suburbs & Illawarra Line",
    "T5": "Cumberland Line", "T6": "Lidcombe & Bankstown Line", "T7": "Olympic Park Line",
    "T8": "Airport & South Line", "T9": "Northern Line",
    "BMT": "Blue Mountains Line", "CCN": "Central Coast & Newcastle Line",
    "SCO": "South Coast Line", "SHL": "Southern Highlands Line", "HUN": "Hunter Line",
}

con = duckdb.connect("analytics.duckdb")

STYLE = """<style>
text{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;fill:#1a1a1a}
.muted{fill:#6a6a6a}.title{font-weight:600}
.bar{fill:#1c7ed6}.line{stroke:#1c7ed6}.dot{fill:#1c7ed6}
.tline{stroke:#e8833a}.tdot{fill:#e8833a}
.grid{stroke:#e2e5ea}.axis{stroke:#c9ccd1}.band{fill:#000;opacity:0.045}
.chip{stroke:#00000022;stroke-width:1}
@media (prefers-color-scheme:dark){
 text{fill:#e8e8e8}.muted{fill:#9aa0a6}
 .bar{fill:#4dabf7}.line{stroke:#4dabf7}.dot{fill:#4dabf7}
 .tline{stroke:#f0a868}.tdot{fill:#f0a868}
 .grid{stroke:#3a3f47}.axis{stroke:#565c66}.band{fill:#fff;opacity:0.06}
 .chip{stroke:#ffffff33}
}
</style>"""


def svg_open(w, h):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'width="100%" role="img">{STYLE}')


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write(name, body):
    with open(os.path.join(OUT, name), "w") as f:
        f.write(body + "</svg>")
    print(f"  wrote {OUT}/{name}")


# ============================================================ chart 1: delay by hour + trips/hour on a second axis
rows = con.execute(f"""
  SELECT (split_part(scheduled_arrival,':',1)::INT % 24) AS hour,
         round(avg(arrival_delay_seconds)/60.0,3) AS avg_min,
         count(DISTINCT trip_id) AS trips
  FROM main_marts.fct_stop_delays WHERE {FRI} AND scheduled_arrival IS NOT NULL
  GROUP BY 1 ORDER BY 1
""").fetchall()
import math
tmax = math.ceil(max(r[2] for r in rows) / 50) * 50   # nice round max for the right axis
W, H = 760, 384
ml, mr, mt, mb = 44, 52, 92, 46
pw, ph = W - ml - mr, H - mt - mb
ymax = 2.0
def yb(v): return mt + ph * (1 - v / ymax)
def yt(t): return mt + ph * (1 - t / tmax)   # right axis (trips)
bw = pw / 24
s = [svg_open(W, H)]
s.append('<text x="0" y="26" class="title" font-size="16">Midday, not rush hour, ran latest</text>')
s.append('<text x="0" y="46" class="muted" font-size="12">Average arrival delay (bars, left axis) with the number of trips running each hour (line, right axis). Friday 18 Sep 2026.</text>')
# legend
s.append('<rect x="0" y="58" width="13" height="12" class="bar"/><text x="18" y="68" font-size="11">avg delay (min)</text>')
s.append('<line x1="150" y1="64" x2="176" y2="64" class="tline" stroke-width="1.5" stroke-opacity="0.6"/><text x="182" y="68" class="muted" font-size="11">trips running</text>')
# shaded windows
def band(h0, h1, label):
    x0 = ml + bw * h0; w = bw * (h1 - h0 + 1)
    s.append(f'<rect x="{x0:.1f}" y="{mt}" width="{w:.1f}" height="{ph}" class="band"/>')
    s.append(f'<text x="{x0 + w/2:.1f}" y="{mt-8}" text-anchor="middle" class="muted" font-size="10.5">{esc(label)}</text>')
band(7, 9, "AM peak"); band(10, 15, "midday"); band(16, 19, "PM peak")
# left gridlines + labels, right-axis labels aligned to the same lines
for frac in [0.25, 0.5, 0.75, 1.0]:
    dv = ymax * frac; y = yb(dv)
    s.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{W-mr}" y2="{y:.1f}" class="grid" stroke-width="1"/>')
    s.append(f'<text x="{ml-6}" y="{y+3.5:.1f}" text-anchor="end" class="muted" font-size="10">{dv:.1f}</text>')
    s.append(f'<text x="{W-mr+6}" y="{y+3.5:.1f}" class="muted" font-size="10">{int(tmax*frac)}</text>')
# bars (solid)
for hour, avg, trips in rows:
    x = ml + bw * hour + bw * 0.15; w = bw * 0.7
    y = yb(avg); hgt = (mt + ph) - y
    s.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{hgt:.1f}" rx="2" class="bar"/>')
# trips line on the right axis — kept deliberately recessive (thin, faded, no markers)
# so the eye stays on the delay bars, which are the main metric.
pts = [(ml + bw * h + bw * 0.5, yt(t)) for (h, a, t) in rows]
s.append(f'<path d="M {" L ".join(f"{x:.1f},{y:.1f}" for x,y in pts)}" fill="none" class="tline" stroke-width="1.5" stroke-opacity="0.6"/>')
for hour in range(0, 24, 3):
    x = ml + bw * hour + bw * 0.5
    s.append(f'<text x="{x:.1f}" y="{mt+ph+18:.1f}" text-anchor="middle" class="muted" font-size="10">{hour:02d}:00</text>')
s.append(f'<text x="{ml}" y="{H-8}" class="muted" font-size="10.5">left: avg arrival delay (min)</text>')
s.append(f'<text x="{W-mr}" y="{H-8}" text-anchor="end" class="muted" font-size="10.5">right: trips running</text>')
write("delay_by_hour.svg", "".join(s))

# ============================================================ chart 2: delay accumulation (unchanged)
rows = con.execute(f"""
  WITH t AS (
    SELECT arrival_delay_seconds, scheduled_stop_sequence,
           max(scheduled_stop_sequence) OVER (PARTITION BY trip_id) AS max_seq
    FROM main_marts.fct_stop_delays WHERE {FRI} AND scheduled_stop_sequence IS NOT NULL
  )
  SELECT (least(9, floor(10.0*scheduled_stop_sequence/nullif(max_seq,0))))::INT AS decile,
         round(avg(arrival_delay_seconds)/60.0,3) AS avg_min
  FROM t WHERE max_seq>0 GROUP BY 1 ORDER BY 1
""").fetchall()
W, H = 760, 384          # extra bottom room for a small train motif
ml, mr, mt, mb = 46, 20, 72, 88
pw, ph = W - ml - mr, H - mt - mb   # plot area unchanged (ph=224) despite taller canvas
ymax = 1.2
def yb2(v): return mt + ph * (1 - v / ymax)
def xb2(i): return ml + pw * (i / 9)
s = [svg_open(W, H)]
s.append('<text x="0" y="26" class="title" font-size="16">Delay builds up as a journey goes on</text>')
s.append('<text x="0" y="46" class="muted" font-size="12">Average arrival delay by position through the trip (start &#8594; end). Trains leave on time and lose it en route.</text>')
for gv in [0.0, 0.3, 0.6, 0.9, 1.2]:
    y = yb2(gv)
    s.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{W-mr}" y2="{y:.1f}" class="grid" stroke-width="1"/>')
    s.append(f'<text x="{ml-6}" y="{y+3.5:.1f}" text-anchor="end" class="muted" font-size="10">{gv:.1f}</text>')
pts = [(xb2(i), yb2(v)) for i, (dec, v) in enumerate(rows)]
path = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
s.append(f'<path d="{path}" fill="none" class="line" stroke-width="2.5"/>')
for x, y in pts:
    s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" class="dot"/>')
s.append(f'<text x="{pts[0][0]:.1f}" y="{pts[0][1]-10:.1f}" text-anchor="middle" font-size="11">{rows[0][1]:.2f} min</text>')
s.append(f'<text x="{pts[-1][0]:.1f}" y="{pts[-1][1]-10:.1f}" text-anchor="end" font-size="11">{rows[-1][1]:.2f} min</text>')
s.append(f'<text x="{ml}" y="{mt+ph+20:.1f}" class="muted" font-size="10.5">trip start</text>')
s.append(f'<text x="{W-mr}" y="{mt+ph+20:.1f}" text-anchor="end" class="muted" font-size="10.5">trip end</text>')
s.append(f'<text x="{(ml+W-mr)/2:.1f}" y="{mt+ph+20:.1f}" text-anchor="middle" class="muted" font-size="10.5">position through journey (deciles)</text>')
# --- small electric-train motif, travelling toward "trip end" (right) ---
tx = (ml + W - mr) / 2 - 36     # body left edge (~centred); body is 72 wide
T = mt + ph + 34                # body top (~330)
BODY_W = 72
# faint dashed track under the wheels, full width
s.append(f'<line x1="{ml}" y1="{T+30:.1f}" x2="{W-mr}" y2="{T+30:.1f}" class="grid" stroke-width="1.5" stroke-dasharray="2 4"/>')
# motion streaks trailing behind (left)
for k, dx in enumerate([-12, -20, -28]):
    s.append(f'<line x1="{tx+dx:.1f}" y1="{T+7+k*5:.1f}" x2="{tx+dx-11:.1f}" y2="{T+7+k*5:.1f}" class="axis" stroke-width="1.5" opacity="0.5"/>')
# pantograph on the roof (electric train cue)
s.append(f'<path d="M {tx+18:.1f},{T} L {tx+24:.1f},{T-7:.1f} L {tx+34:.1f},{T:.1f}" fill="none" class="axis" stroke-width="1.2"/>')
s.append(f'<line x1="{tx+20:.1f}" y1="{T-7:.1f}" x2="{tx+32:.1f}" y2="{T-7:.1f}" class="axis" stroke-width="1.4"/>')
# body: rounded rect with a swept-down cab front on the right
s.append(f'<path d="M {tx:.1f},{T+5:.1f} Q {tx:.1f},{T:.1f} {tx+5:.1f},{T:.1f} '
         f'H {tx+BODY_W-14:.1f} Q {tx+BODY_W:.1f},{T:.1f} {tx+BODY_W:.1f},{T+12:.1f} '
         f'V {T+18:.1f} Q {tx+BODY_W:.1f},{T+22:.1f} {tx+BODY_W-4:.1f},{T+22:.1f} '
         f'H {tx+4:.1f} Q {tx:.1f},{T+22:.1f} {tx:.1f},{T+17:.1f} Z" class="muted"/>')
# livery stripe along the lower body
s.append(f'<rect x="{tx+2:.1f}" y="{T+15:.1f}" width="{BODY_W-6:.1f}" height="3" rx="1.5" class="bar" opacity="0.85"/>')
# passenger windows (row of 4) + slanted cab windscreen at the front
for wx in range(0, 4):
    s.append(f'<rect x="{tx+7+wx*13:.1f}" y="{T+5:.1f}" width="9" height="6" rx="1.5" fill="#ffffff" opacity="0.5"/>')
s.append(f'<path d="M {tx+BODY_W-11:.1f},{T+5:.1f} H {tx+BODY_W-3:.1f} L {tx+BODY_W-2:.1f},{T+11:.1f} H {tx+BODY_W-11:.1f} Z" fill="#ffffff" opacity="0.5"/>')
# two bogies (pairs of wheels) rather than two lone circles
for cx in [tx+15, tx+BODY_W-17]:
    s.append(f'<circle cx="{cx-5:.1f}" cy="{T+25:.1f}" r="3" class="muted"/><circle cx="{cx+5:.1f}" cy="{T+25:.1f}" r="3" class="muted"/>')
write("delay_accumulation.svg", "".join(s))

# ============================================================ chart 3: % of TRIPS with >=1 late stop, by line (real colours)
allrows = con.execute(f"""
  WITH trip_flags AS (
    SELECT trip_id, route_short_name,
           max(CASE WHEN arrival_delay_seconds>300 THEN 1 ELSE 0 END) AS had_late
    FROM main_marts.fct_stop_delays WHERE {FRI} AND route_short_name IS NOT NULL
    GROUP BY trip_id, route_short_name
  )
  SELECT route_short_name,
         count(*) AS trips,
         sum(had_late) AS late_trips,
         round(100.0*sum(had_late)/count(*),1) AS pct_trips_late
  FROM trip_flags GROUP BY 1 HAVING count(*)>=20 ORDER BY pct_trips_late DESC
""").fetchall()
top5 = allrows[:5]
bot5 = list(reversed(allrows[-5:]))   # least delay-prone on top, ascending
items = [("H", "Most delay-prone")] + [("R",) + r for r in top5] + [("H", "Least delay-prone")] + [("R",) + r for r in bot5]
# Label sits ABOVE each bar (line names are long); grouped top-5 / bottom-5 like the station chart.
W = 760; rowh = 44; hh = 30; mt = 68; mb = 22; valw = 150
pw = W - valw
xmax = max(r[3] for r in top5) * 1.02
n_r = sum(1 for it in items if it[0] == "R"); n_h = sum(1 for it in items if it[0] == "H")
H = mt + rowh * n_r + hh * n_h + mb
s = [svg_open(W, H)]
s.append('<text x="0" y="26" class="title" font-size="16">How often a line ran a late trip</text>')
s.append('<text x="0" y="46" class="muted" font-size="12">Share of trips with at least one stop arriving &gt;5 min late, by line. Bars use each line’s official colour. Friday 18 Sep 2026.</text>')
y = mt
for it in items:
    if it[0] == "H":
        s.append(f'<text x="0" y="{y+18:.1f}" class="muted" font-size="11" font-weight="600" letter-spacing="0.06em">{esc(it[1]).upper()}</text>')
        y += hh
    else:
        _, route, trips, late, pct = it
        bw_ = max(pw * (pct / xmax), 2)
        color = LINE_COLORS.get(route, DEFAULT_LINE)
        name = LINE_NAMES.get(route, "")
        s.append(f'<text x="0" y="{y+12:.1f}" font-size="12"><tspan class="title">{esc(route)}</tspan> <tspan class="muted">· {esc(name)}</tspan></text>')
        s.append(f'<rect x="0" y="{y+18:.1f}" width="{bw_:.1f}" height="14" rx="3" fill="{color}" class="chip"/>')
        s.append(f'<text x="{bw_+8:.1f}" y="{y+29:.1f}" font-size="11">{pct:.1f}%  <tspan class="muted">({late} of {trips} trips)</tspan></text>')
        y += rowh
write("late_trips_by_line.svg", "".join(s))

# ============================================================ chart 4: top 8 stations by late arrivals
rows = con.execute(f"""
  SELECT station, count(*) AS stops,
         round(100.0*count(*) FILTER (WHERE arrival_delay_seconds>300)/count(*),1) AS pct_late
  FROM main_marts.fct_stop_delays WHERE {FRI}
  GROUP BY 1 HAVING count(*)>=150 ORDER BY pct_late DESC, stops DESC LIMIT 8
""").fetchall()
W = 760; rowh = 30; mt = 72; ml = 170; mr = 66; mb = 26
H = mt + rowh * len(rows) + mb
pw = W - ml - mr
xmax = max(r[2] for r in rows) * 1.15
s = [svg_open(W, H)]
s.append('<text x="0" y="26" class="title" font-size="16">The stations that saw the most late arrivals</text>')
s.append('<text x="0" y="46" class="muted" font-size="12">Top 8 stations by share of arrivals more than 5 min late (≥150 arrivals). Friday 18 Sep 2026.</text>')
for i, (station, stops, pct) in enumerate(rows):
    y = mt + i * rowh
    name = station.replace(" Station", "")
    bw_ = pw * (pct / xmax)
    s.append(f'<text x="{ml-8}" y="{y+rowh/2+4:.1f}" text-anchor="end" font-size="11.5">{esc(name)}</text>')
    s.append(f'<rect x="{ml}" y="{y+5:.1f}" width="{max(bw_,2):.1f}" height="{rowh-12:.1f}" rx="3" class="bar"/>')
    s.append(f'<text x="{ml+max(bw_,2)+6:.1f}" y="{y+rowh/2+4:.1f}" font-size="11">{pct:.1f}%  <tspan class="muted">({stops})</tspan></text>')
write("late_arrivals_by_station.svg", "".join(s))

con.close()
print("Done.")
