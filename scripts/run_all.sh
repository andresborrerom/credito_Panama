#!/usr/bin/env bash
# Re-construir TODO el estudio desde cero.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> 1/4 Extract (Latinex + UST)"
python3 -m src.etl.extract

echo "==> 2/4 Transform (DB SQLite + Parquet, cálculo YTM)"
python3 -m src.etl.transform

echo "==> 3/4 Static site (docs/)"
python3 -m src.app.build_site

echo "==> 4/4 PDF report"
python3 -m src.app.build_pdf

echo
echo "Listo. Ver:"
echo "  - docs/index.html      (sitio mobile-friendly)"
echo "  - docs/estudio_renta_fija_panama.pdf"
echo "  - data/panama_fixed_income.sqlite"
echo
echo "Streamlit local:"
echo "  streamlit run src/app/streamlit_app.py"
