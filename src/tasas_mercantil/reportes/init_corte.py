"""Inicializa un folder de corte nuevo con templates YAML editables.

Uso:
    python -m src.tasas_mercantil.reportes.init_corte --corte 2026-06 --as-of 2026-06-30

Copia los YAML del corte previo como punto de partida (continuidad editorial
y trigger calendar para el próximo mes). El usuario edita los campos.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import date
from pathlib import Path


CORTES_DIR = Path("ProyectoTasasMercantil/cortes")


def init_corte(corte_nuevo: str, as_of: str, corte_template: str = "2026-05") -> Path:
    src = CORTES_DIR / corte_template
    dst = CORTES_DIR / corte_nuevo

    if not src.exists():
        raise FileNotFoundError(f"Corte template {src} no existe")
    if dst.exists():
        raise FileExistsError(f"Corte destino {dst} ya existe")

    dst.mkdir(parents=True)
    (dst / "input").mkdir(exist_ok=True)
    (dst / "narrativa").mkdir(exist_ok=True)
    (dst / "output_v10").mkdir(exist_ok=True)

    # Copiar YAMLs y dejar nota de "actualizar todos los campos"
    for yaml_name in ["narrativa.yaml", "venezuela.yaml"]:
        src_yaml = src / yaml_name
        if not src_yaml.exists():
            continue
        dst_yaml = dst / yaml_name
        text = src_yaml.read_text()
        # Reemplazar identificadores del corte previo con el nuevo
        text = text.replace(f'"{corte_template}"', f'"{corte_nuevo}"')
        # Bandera al inicio del archivo
        header = (
            f"# CORTE {corte_nuevo} — INICIADO DESDE TEMPLATE {corte_template}\n"
            f"# Actualiza todos los campos antes de renderizar.\n\n"
        )
        dst_yaml.write_text(header + text)
        print(f"  Creado: {dst_yaml}")

    # Cierre placeholder
    cierre_md = dst / "cierre.md"
    cierre_md.write_text(
        f"# Cierre · Corte {corte_nuevo}\n\n"
        f"> Pendiente de redacción al finalizar el corte. Ver "
        f"05_MEMORIA_DE_SESIONES.md para la plantilla obligatoria.\n"
    )
    print(f"  Creado: {cierre_md}")

    return dst


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corte", required=True, help="YYYY-MM del corte nuevo")
    ap.add_argument("--as-of", required=True, help="YYYY-MM-DD del cierre")
    ap.add_argument("--template", default="2026-05", help="Corte a copiar como template")
    args = ap.parse_args()

    dst = init_corte(args.corte, args.as_of, args.template)
    print(f"\n[OK] Corte {args.corte} inicializado en {dst}")
    print(f"\nProximos pasos:")
    print(f"  1. Edita {dst}/narrativa.yaml (TL;DR, tactical views, calendario).")
    print(f"  2. Edita {dst}/venezuela.yaml (BCV + FX + bonos).")
    print(f"  3. El analista deja la plantilla Bloomberg en {dst}/input/.")
    print(f"  4. Corre: python -m src.tasas_mercantil.reportes.render_deck_v10 \\")
    print(f"            --as-of {args.as_of} --corte {args.corte}")
    print(f"  5. Revisa output_v10/TasasMercantil_{args.corte}_v10.pdf.")
    print(f"  6. Al cerrar, redacta {dst}/cierre.md.")


if __name__ == "__main__":
    main()
