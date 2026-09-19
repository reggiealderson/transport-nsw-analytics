#!/usr/bin/env bash
# Regenerate the article's charts, diagrams, and dbt docs, then copy them into the
# portfolio site. Run from the transport_nsw_analytics repo root.
#
#   ./copy_to_portfolio.sh
#
# Mirrors the pattern used for the skill-graph sub-app: build artifacts live here,
# the portfolio just hosts the output under public/.
set -euo pipefail

PORTFOLIO="/Users/reggiealderson/Documents/projects/personal_portfolio_website"
IMG_DEST="$PORTFOLIO/public/images/articles/train-delays"
DOCS_DEST="$PORTFOLIO/public/train-delays-dbt-docs"

echo "==> regenerating charts + diagrams"
.venv/bin/python make_charts.py
.venv/bin/python make_diagrams.py

echo "==> copying chart/diagram SVGs -> $IMG_DEST"
mkdir -p "$IMG_DEST"
cp charts/*.svg "$IMG_DEST/"

echo "==> regenerating dbt docs (single static file) -> $DOCS_DEST"
( cd dbt && ../.venv/bin/dbt docs generate --static --profiles-dir . >/dev/null )
mkdir -p "$DOCS_DEST"
cp dbt/target/static_index.html "$DOCS_DEST/index.html"

echo "==> done. Served at /images/articles/train-delays/*.svg and /train-delays-dbt-docs/"
