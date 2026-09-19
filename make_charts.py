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

con = duckdb.connect("analytics.duckdb")

# House palette (matches the existing article's SVGs).
STYLE = """<style>
text{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;fill:#1a1a1a}
.muted{fill:#6a6a6a}.title{font-weight:600}
.bar{fill:#1c7ed6}.line{stroke:#1c7ed6}.dot{fill:#1c7ed6}
.grid{stroke:#e2e5ea}.axis{stroke:#c9ccd1}.band{fill:#000;opacity:0.045}
@media (prefers-color-scheme:dark){
 text{fill:#e8e8e8}.muted{fill:#9aa0a6}
 .bar{fill:#4dabf7}.line{stroke:#4dabf7}.dot{fill:#4dabf7}
 .grid{stroke:#3a3f47}.axis{stroke:#565c66}.band{fill:#fff;opacity:0.06}
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


# ---------------------------------------------------------------- chart 1: delay by hour
rows = con.execute(f"""
  SELECT (split_part(scheduled_arrival,':',1)::INT % 24) AS hour,
         round(avg(arrival_delay_seconds)/60.0,3) AS avg_min
  FROM main_marts.fct_stop_delays WHERE {FRI} AND scheduled_arrival IS NOT NULL
  GROUP BY 1 ORDER BY 1
""").fetchall()
W, H = 760, 360
ml, mr, mt, mb = 44, 16, 74, 46
pw, ph = W - ml - mr, H - mt - mb
ymax = 2.0
def yb(v): return mt + ph * (1 - v / ymax)
bw = pw / 24
s = [svg_open(W, H)]
s.append(f'<text x="0" y="26" class="title" font-size="16">Midday, not rush hour, ran latest</text>')
s.append(f'<text x="0" y="46" class="muted" font-size="12">Average arrival delay by scheduled hour — Friday 18 Sep 2026, estimated-actual readings.</text>')
# shaded windows
def band(h0, h1, label):
    x0 = ml + bw * h0
    w = bw * (h1 - h0 + 1)
    s.append(f'<rect x="{x0:.1f}" y="{mt}" width="{w:.1f}" height="{ph}" class="band"/>')
    s.append(f'<text x="{x0 + w/2:.1f}" y="{mt-8}" text-anchor="middle" class="muted" font-size="10.5">{esc(label)}</text>')
band(7, 9, "AM peak")
band(10, 15, "midday")
band(16, 19, "PM peak")
# y gridlines
for gv in [0.5, 1.0, 1.5, 2.0]:
    y = yb(gv)
    s.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{W-mr}" y2="{y:.1f}" class="grid" stroke-width="1"/>')
    s.append(f'<text x="{ml-6}" y="{y+3.5:.1f}" text-anchor="end" class="muted" font-size="10">{gv:.1f}</text>')
s.append(f'<text x="{ml-6}" y="{mt-56}" class="muted" font-size="0"></text>')
# bars
for hour, avg in rows:
    x = ml + bw * hour + bw * 0.15
    w = bw * 0.7
    y = yb(avg); hgt = (mt + ph) - y
    s.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{hgt:.1f}" rx="2" class="bar"/>')
# x axis labels (every 3h)
for hour in range(0, 24, 3):
    x = ml + bw * hour + bw * 0.5
    s.append(f'<text x="{x:.1f}" y="{mt+ph+18:.1f}" text-anchor="middle" class="muted" font-size="10">{hour:02d}:00</text>')
s.append(f'<text x="{ml}" y="{H-8}" class="muted" font-size="10.5">y-axis: average arrival delay (minutes)</text>')
write("delay_by_hour.svg", "".join(s))

# ---------------------------------------------------------------- chart 2: delay accumulation
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
W, H = 760, 340
ml, mr, mt, mb = 46, 20, 72, 44
pw, ph = W - ml - mr, H - mt - mb
ymax = 1.2
def yb2(v): return mt + ph * (1 - v / ymax)
def xb2(i): return ml + pw * (i / 9)
s = [svg_open(W, H)]
s.append(f'<text x="0" y="26" class="title" font-size="16">Delay builds up as a journey goes on</text>')
s.append(f'<text x="0" y="46" class="muted" font-size="12">Average arrival delay by position through the trip (start &#8594; end). Trains leave on time and lose it en route.</text>')
for gv in [0.0, 0.3, 0.6, 0.9, 1.2]:
    y = yb2(gv)
    s.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{W-mr}" y2="{y:.1f}" class="grid" stroke-width="1"/>')
    s.append(f'<text x="{ml-6}" y="{y+3.5:.1f}" text-anchor="end" class="muted" font-size="10">{gv:.1f}</text>')
pts = [(xb2(i), yb2(v)) for i, (dec, v) in enumerate(rows)]
path = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
s.append(f'<path d="{path}" fill="none" class="line" stroke-width="2.5"/>')
for i, (x, y) in enumerate(pts):
    s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" class="dot"/>')
# direct-label first and last
s.append(f'<text x="{pts[0][0]:.1f}" y="{pts[0][1]-10:.1f}" text-anchor="middle" font-size="11">{rows[0][1]:.2f} min</text>')
s.append(f'<text x="{pts[-1][0]:.1f}" y="{pts[-1][1]-10:.1f}" text-anchor="end" font-size="11">{rows[-1][1]:.2f} min</text>')
s.append(f'<text x="{ml}" y="{mt+ph+20:.1f}" class="muted" font-size="10.5">trip start</text>')
s.append(f'<text x="{W-mr}" y="{mt+ph+20:.1f}" text-anchor="end" class="muted" font-size="10.5">trip end</text>')
s.append(f'<text x="{(ml+W-mr)/2:.1f}" y="{mt+ph+20:.1f}" text-anchor="middle" class="muted" font-size="10.5">position through journey (deciles)</text>')
write("delay_accumulation.svg", "".join(s))

# ---------------------------------------------------------------- chart 3: worst lines
rows = con.execute(f"""
  SELECT route_short_name,
         round(100.0*count(*) FILTER (WHERE arrival_delay_seconds>300)/count(*),1) AS pct_late,
         count(*) AS stops
  FROM main_marts.fct_stop_delays WHERE {FRI} AND route_short_name IS NOT NULL
  GROUP BY 1 HAVING count(*)>=200 ORDER BY pct_late DESC LIMIT 8
""").fetchall()
W = 760
rowh = 30
mt = 72; ml = 60; mr = 60; mb = 30
H = mt + rowh * len(rows) + mb
pw = W - ml - mr
xmax = max(r[1] for r in rows) * 1.15
s = [svg_open(W, H)]
s.append(f'<text x="0" y="26" class="title" font-size="16">Even the least-punctual lines were rarely late</text>')
s.append(f'<text x="0" y="46" class="muted" font-size="12">Share of stops arriving more than 5 minutes late, by line — Friday 18 Sep 2026.</text>')
for i, (route, pct, stops) in enumerate(rows):
    y = mt + i * rowh
    bw_ = pw * (pct / xmax)
    s.append(f'<text x="{ml-8}" y="{y+rowh/2+4:.1f}" text-anchor="end" font-size="12">{esc(route)}</text>')
    s.append(f'<rect x="{ml}" y="{y+5:.1f}" width="{bw_:.1f}" height="{rowh-12:.1f}" rx="3" class="bar"/>')
    s.append(f'<text x="{ml+bw_+6:.1f}" y="{y+rowh/2+4:.1f}" font-size="11">{pct:.1f}%</text>')
write("worst_lines.svg", "".join(s))

con.close()
print("Done.")
