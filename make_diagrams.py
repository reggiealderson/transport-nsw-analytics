"""
Generate the hero banner and the inputs->processes->outputs system diagram for the
"One Delayed Friday" article, in the same theme-aware house style as the charts.

Output: charts/hero.svg, charts/pipeline.svg
Run:  .venv/bin/python make_diagrams.py
"""
import os
import duckdb

OUT = "charts"
os.makedirs(OUT, exist_ok=True)
FRI = "service_date = DATE '2026-09-18' AND arrival_delay_seconds IS NOT NULL AND abs(arrival_delay_seconds) <= 3*3600"

STYLE = """<style>
text{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;fill:#1a1a1a}
.muted{fill:#6a6a6a}.title{font-weight:600}
.bar{fill:#1c7ed6}.accent{fill:#1c7ed6}
.box{fill:#ffffff;stroke:#d4d9e0}.obox{fill:#eef5fc;stroke:#9dc4ea}
.track{stroke:#c9ccd1}.arrow{stroke:#9aa0a6;fill:none}
@media (prefers-color-scheme:dark){
 text{fill:#e8e8e8}.muted{fill:#9aa0a6}
 .bar{fill:#4dabf7}.accent{fill:#4dabf7}
 .box{fill:#1b2029;stroke:#333b45}.obox{fill:#132232;stroke:#2f5372}
 .track{stroke:#565c66}.arrow{stroke:#6b7480}
}
</style>"""


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def train(tx, T, scale=1.0):
    """Reusable electric-train silhouette facing right (same design as chart 2)."""
    W = 72 * scale
    g = []
    g.append(f'<path d="M {tx+18*scale:.1f},{T:.1f} L {tx+24*scale:.1f},{T-7*scale:.1f} L {tx+34*scale:.1f},{T:.1f}" fill="none" class="track" stroke-width="1.2"/>')
    g.append(f'<line x1="{tx+20*scale:.1f}" y1="{T-7*scale:.1f}" x2="{tx+32*scale:.1f}" y2="{T-7*scale:.1f}" class="track" stroke-width="1.4"/>')
    g.append(f'<path d="M {tx:.1f},{T+5*scale:.1f} Q {tx:.1f},{T:.1f} {tx+5*scale:.1f},{T:.1f} '
             f'H {tx+W-14*scale:.1f} Q {tx+W:.1f},{T:.1f} {tx+W:.1f},{T+12*scale:.1f} '
             f'V {T+18*scale:.1f} Q {tx+W:.1f},{T+22*scale:.1f} {tx+W-4*scale:.1f},{T+22*scale:.1f} '
             f'H {tx+4*scale:.1f} Q {tx:.1f},{T+22*scale:.1f} {tx:.1f},{T+17*scale:.1f} Z" class="muted"/>')
    g.append(f'<rect x="{tx+2*scale:.1f}" y="{T+15*scale:.1f}" width="{W-6*scale:.1f}" height="{3*scale:.1f}" rx="1.5" class="bar" opacity="0.85"/>')
    for wx in range(4):
        g.append(f'<rect x="{tx+(7+wx*13)*scale:.1f}" y="{T+5*scale:.1f}" width="{9*scale:.1f}" height="{6*scale:.1f}" rx="1.5" fill="#ffffff" opacity="0.5"/>')
    g.append(f'<path d="M {tx+(W/scale-11)*scale:.1f},{T+5*scale:.1f} H {tx+(W/scale-3)*scale:.1f} L {tx+(W/scale-2)*scale:.1f},{T+11*scale:.1f} H {tx+(W/scale-11)*scale:.1f} Z" fill="#ffffff" opacity="0.5"/>')
    for cx in [tx+15*scale, tx+(72-17)*scale]:
        g.append(f'<circle cx="{cx-5*scale:.1f}" cy="{T+25*scale:.1f}" r="{3*scale:.1f}" class="muted"/><circle cx="{cx+5*scale:.1f}" cy="{T+25*scale:.1f}" r="{3*scale:.1f}" class="muted"/>')
    return "".join(g)


# ------------------------------------------------------------------ hero
con = duckdb.connect("analytics.duckdb")
hours = con.execute(f"""
  SELECT (split_part(scheduled_arrival,':',1)::INT % 24) AS h,
         round(avg(arrival_delay_seconds)/60.0,3) AS avg_min
  FROM main_marts.fct_stop_delays WHERE {FRI} AND scheduled_arrival IS NOT NULL
  GROUP BY 1 ORDER BY 1
""").fetchall()
con.close()

W, H = 760, 190
s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img">{STYLE}']
# faint "skyline" of the day's hourly delays across the bottom
bx0, bw = 24, (W - 48) / 24
base = 150
ymax = max(h[1] for h in hours)
for h, v in hours:
    bh = 8 + 58 * (v / ymax)
    s.append(f'<rect x="{bx0 + h*bw + 1:.1f}" y="{base - bh:.1f}" width="{bw-2:.1f}" height="{bh:.1f}" rx="1.5" class="bar" opacity="0.16"/>')
# track the train rides on
s.append(f'<line x1="24" y1="{base:.1f}" x2="{W-24}" y2="{base:.1f}" class="track" stroke-width="1.5"/>')
for i in range(9):
    x = 24 + i * (W - 48) / 8
    s.append(f'<circle cx="{x:.1f}" cy="{base:.1f}" r="2.5" class="track" fill="none" stroke-width="1.5"/>')
# a "scheduled vs actual" gap marker (no labels — the banner carries no text)
sched_x = 560
s.append(f'<line x1="{sched_x}" y1="{base-30:.1f}" x2="{sched_x}" y2="{base+8:.1f}" class="track" stroke-width="1.4" stroke-dasharray="3 3"/>')
# the train, running a little behind the scheduled mark, with a gap indicator
s.append(train(452, base - 22, scale=1.15))
s.append(f'<line x1="524" y1="{base-30:.1f}" x2="{sched_x-2}" y2="{base-30:.1f}" class="arrow" stroke-width="1.4"/>')
s.append("</svg>")
with open(f"{OUT}/hero.svg", "w") as f:
    f.write("".join(s))
print(f"  wrote {OUT}/hero.svg")


# ------------------------------------------------------------------ pipeline (inputs -> processes -> outputs)
W, H = 760, 380
s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img">{STYLE}']
s.append('<text x="0" y="22" class="title" font-size="15">From live feed to governed data</text>')
s.append('<text x="0" y="42" class="muted" font-size="12">Inputs are collected, transformed and tested, then published as analysis-ready and governance artifacts.</text>')

colx = {"in": 8, "proc": 292, "out": 576}
colw = {"in": 176, "proc": 200, "out": 176}
for key, label, cx in [("in", "INPUTS", colx["in"]), ("proc", "PROCESSES", colx["proc"]), ("out", "OUTPUTS", colx["out"])]:
    s.append(f'<text x="{cx}" y="72" class="muted" font-size="11" font-weight="600" letter-spacing="0.08em">{label}</text>')


def box(x, y, w, h, lines, cls="box"):
    s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" class="{cls}" stroke-width="1.2"/>')
    n = len(lines)
    for i, (ln, sub) in enumerate(lines):
        ty = y + h/2 + (i - (n-1)/2) * 16 + 4
        if sub:
            s.append(f'<text x="{x+w/2}" y="{ty:.1f}" text-anchor="middle" class="muted" font-size="11">{esc(ln)}</text>')
        else:
            s.append(f'<text x="{x+w/2}" y="{ty:.1f}" text-anchor="middle" font-size="12" class="title">{esc(ln)}</text>')


# inputs
box(colx["in"], 88, colw["in"], 52, [("GTFS static schedule", False), ("daily ZIP · trips, stops", True)])
box(colx["in"], 156, colw["in"], 52, [("GTFS-Realtime", False), ("trip updates · every 10s", True)])
# processes
box(colx["proc"], 88, colw["proc"], 46, [("poll_rt.py", False), ("60s snapshots → DuckDB", True)])
box(colx["proc"], 150, colw["proc"], 46, [("dbt models", False), ("staging → intermediate → mart", True)])
box(colx["proc"], 212, colw["proc"], 46, [("23 quality tests", False), ("DAMA-DMBOK dimensions", True)])
# outputs
box(colx["out"], 84, colw["out"], 40, [("fct_stop_delays", False)], cls="obox")
box(colx["out"], 132, colw["out"], 40, [("quality scorecard", False)], cls="obox")
box(colx["out"], 180, colw["out"], 40, [("PIA-lite classification", False)], cls="obox")
box(colx["out"], 228, colw["out"], 40, [("dbt docs · lineage", False)], cls="obox")

# arrows: inputs -> processes (into poll_rt), processes chain, processes -> outputs
def arrow(x1, y1, x2, y2):
    s.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2-6:.1f}" y2="{y2:.1f}" class="arrow" stroke-width="1.4"/>')
    s.append(f'<path d="M {x2-6:.1f},{y2-4:.1f} L {x2:.1f},{y2:.1f} L {x2-6:.1f},{y2+4:.1f}" class="arrow" stroke-width="1.4"/>')

ax_in = colx["in"] + colw["in"]; ax_proc = colx["proc"]; ax_proc_r = colx["proc"] + colw["proc"]; ax_out = colx["out"]
arrow(ax_in, 114, ax_proc, 111)
arrow(ax_in, 182, ax_proc, 111)
# chain within processes (vertical, downward)
def varrow(x, y1, y2):
    s.append(f'<line x1="{x:.1f}" y1="{y1:.1f}" x2="{x:.1f}" y2="{y2-6:.1f}" class="arrow" stroke-width="1.4"/>')
    s.append(f'<path d="M {x-4:.1f},{y2-6:.1f} L {x:.1f},{y2:.1f} L {x+4:.1f},{y2-6:.1f}" class="arrow" stroke-width="1.4"/>')
pcx = colx["proc"] + colw["proc"] / 2
varrow(pcx, 134, 150)   # poll -> dbt
varrow(pcx, 196, 212)   # dbt -> tests
# processes -> outputs (fan out from the dbt/tests block)
for oy in [104, 152, 200, 248]:
    arrow(ax_proc_r, 190, ax_out, oy)
s.append("</svg>")
with open(f"{OUT}/pipeline.svg", "w") as f:
    f.write("".join(s))
print(f"  wrote {OUT}/pipeline.svg")


# ------------------------------------------------------------------ governance injection diagram
W, H = 760, 322
s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img">{STYLE}']
s.append('<text x="0" y="22" class="title" font-size="15">Where governance enters the pipeline</text>')
s.append('<text x="0" y="42" class="muted" font-size="12">Tests, classification and descriptions attach to each dbt model; the artifacts below are generated from them.</text>')

sw, sh, sy = 150, 40, 66
stages = [("Raw feeds", 8), ("Staging", 196), ("Intermediate", 384), ("Mart", 572)]
for name, x in stages:
    s.append(f'<rect x="{x}" y="{sy}" width="{sw}" height="{sh}" rx="8" class="box" stroke-width="1.2"/>')
    s.append(f'<text x="{x+sw/2}" y="{sy+sh/2+4}" text-anchor="middle" class="title" font-size="12">{esc(name)}</text>')
for x in [8, 196, 384]:
    arrow(x+sw, sy+sh/2, x+188, sy+sh/2)

# governance band under Staging..Mart
bx, by, bw, bh = 196, 128, 526, 60
s.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="10" class="obox" stroke-width="1.2"/>')
s.append(f'<text x="{bx+14}" y="{by+17}" class="muted" font-size="10.5" font-weight="600" letter-spacing="0.07em">GOVERNANCE, APPLIED AT EACH MODEL</text>')
for label, x in [("quality tests (DAMA)", 210), ("classification tags", 380), ("column descriptions", 550)]:
    s.append(f'<rect x="{x}" y="{by+28}" width="158" height="22" rx="6" class="box" stroke-width="1"/>')
    s.append(f'<text x="{x+79}" y="{by+43}" text-anchor="middle" font-size="10.5">{esc(label)}</text>')
# dashed connectors: model stages drop into the band
for x in [196, 384, 572]:
    s.append(f'<line x1="{x+sw/2}" y1="{sy+sh}" x2="{x+sw/2}" y2="{by}" class="track" stroke-width="1" stroke-dasharray="2 3"/>')

# outputs generated from the governance layer
oy, oh = 240, 44
outs = [("Quality", "scorecard", 196), ("Data dictionary", "+ lineage graph", 384), ("Privacy +", "policy docs", 572)]
for l1, l2, x in outs:
    s.append(f'<rect x="{x}" y="{oy}" width="{sw}" height="{oh}" rx="8" class="obox" stroke-width="1.2"/>')
    s.append(f'<text x="{x+sw/2}" y="{oy+19}" text-anchor="middle" font-size="11.5" class="title">{esc(l1)}</text>')
    s.append(f'<text x="{x+sw/2}" y="{oy+34}" text-anchor="middle" font-size="11.5" class="title">{esc(l2)}</text>')
for x in [196, 384, 572]:
    varrow(x+sw/2, by+bh, oy)
s.append("</svg>")
with open(f"{OUT}/governance.svg", "w") as f:
    f.write("".join(s))
print(f"  wrote {OUT}/governance.svg")
print("Done.")
