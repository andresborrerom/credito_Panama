"""Refresh end-to-end del deck informativo, sin depender de la plantilla BBG.

Pasos:
  1. Descarga FRED (curvas UST + TIPS + breakeven + SOFR + IORB).
  2. Descarga EODHD FX (G10 + DXY).
  3. Re-fetch del último SEP de la Fed (si hay uno nuevo, lo agrega).
  4. Regenera las 7 láminas + deck consolidado para el `as_of` indicado
     (default: hoy).

Uso:
    PYTHONPATH=src python scripts/refresh_informativa.py             # hoy
    PYTHONPATH=src python scripts/refresh_informativa.py 2026-06-17  # corte específico
"""
from __future__ import annotations
import os
import sys
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(args, env=None):
    print(f"\n$ {' '.join(args)}", flush=True)
    subprocess.run(args, cwd=ROOT, check=True,
                   env={**os.environ, **(env or {})})


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    as_of = date.fromisoformat(arg)
    print(f"=== Refresh informativa · as_of = {as_of} ===")

    env = {"PYTHONPATH": "src"}

    # 1) FRED curvas USA (no requiere API key)
    _run(["python", "scripts/ingest_a3_fred_curvas.py"], env=env)

    # 2) EODHD FX (requiere EODHD_API_KEY)
    if os.environ.get("EODHD_API_KEY"):
        _run(["python", "scripts/ingest_a2_eodhd_fx.py"], env=env)
    else:
        print("\n[skip] EODHD_API_KEY no está en entorno — FX queda con cache")

    # 2.5) Si hay Excel Bloomberg subido para el corte, procesarlo
    bbg_xlsx = ROOT / "ProyectoTasasMercantil" / "cortes" / str(as_of) / "BloombergTemplate.xlsx"
    if bbg_xlsx.exists():
        print(f"\n[BBG] Excel encontrado: {bbg_xlsx}")
        _run(["python", "scripts/ingest_bloomberg_template.py", str(bbg_xlsx)],
             env=env)
    else:
        print(f"\n[skip] No hay {bbg_xlsx} — slides BBG-dependientes "
              "(forwards FX, CDS Panamá, ECFC) usan último cargado o quedan sin dato")

    # 3) Regenerar slides (PNG sin banner), messages.json, site HTML, deck
    code = f"""
from datetime import date
from tasas_mercantil.informativa.modelo_combinado import plot_l_usa_0
from tasas_mercantil.informativa.fed_dotplot      import plot_l_usa_1
from tasas_mercantil.informativa.path_fed          import plot_path_fed
from tasas_mercantil.informativa.curvas_usa        import plot_curvas_usa
from tasas_mercantil.informativa.fx_g10            import plot_l_fx_1
from tasas_mercantil.informativa.panama_corp       import plot_l_pa_1
from tasas_mercantil.informativa.panama_soberano   import plot_l_pa_2
from tasas_mercantil.informativa.deck              import compile_informativa
from tasas_mercantil.informativa.messages          import save_messages_json
from tasas_mercantil.informativa.site              import render_site, render_index
import os
as_of = date.fromisoformat('{as_of}')
out_dir = f'docs/informativa/outputs/{{as_of}}'
os.makedirs(out_dir, exist_ok=True)
# 3.1 PNGs sin banner (el mensaje irá editable en el PPT y el site)
plot_l_usa_0(as_of, f'{{out_dir}}/L_USA_0_modelo_combinado.png')
plot_l_usa_1(as_of, f'{{out_dir}}/L_USA_1_dotplot.png')
plot_path_fed(as_of, f'{{out_dir}}/L_USA_2_path_fed.png')
plot_curvas_usa(as_of, f'{{out_dir}}/L_USA_3_curvas_usa.png')
plot_l_fx_1(as_of, f'{{out_dir}}/L_FX_1_g10.png')
plot_l_pa_1(as_of, f'{{out_dir}}/L_PA_1_corp_sector_plazo.png')
plot_l_pa_2(as_of, f'{{out_dir}}/L_PA_2_soberano.png')
# 3.2 messages.json (propuesta autogenerada, conserva ediciones previas)
mp = save_messages_json(as_of)
print(f'messages.json → {{mp}}')
# 3.3 site HTML por corte + index global
sp = render_site(as_of); print(f'site → {{sp}}')
ip = render_index();     print(f'index → {{ip}}')
# 3.4 PPT con mensajes (toma edits de messages.json si existen)
out, inc, pend = compile_informativa(as_of)
print(f'DECK: {{out}}  ({{len(inc)}} slides)')
"""
    _run(["python", "-c", code], env=env)

    # 4) Mostrar resumen de freshness
    code2 = """
from tasas_mercantil.informativa.data_loader import freshness_summary
df = freshness_summary()
print('\\n=== Fuente y fecha de cada feature usada en el deck ===')
print(df.to_string(index=False))
"""
    _run(["python", "-c", code2], env=env)


if __name__ == "__main__":
    main()
