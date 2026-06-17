"""API canónica de mensajes propuestos por slide.

Cada función computa el mensaje principal de su slide a partir de los datos
del corte. NO renderiza PNG — eso lo hacen los plot_* respectivos.

El mensaje propuesto es **editable**: se serializa a messages.json y el
site (docs/informativa/index.html) permite editarlo antes de compilar el
deck final. El deck.py admite un dict de overrides que reemplaza el
propuesto por el editado.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import json


SLUG_ORDER = [
    "L_USA_0_modelo_combinado",
    "L_USA_1_dotplot",
    "L_USA_2_path_fed",
    "L_USA_3_curvas_usa",
    "L_FX_1_g10",
    "L_PA_1_corp_sector_plazo",
    "L_PA_2_soberano",
]

SLUG_TITLES = {
    "L_USA_0_modelo_combinado": "Por qué combinamos WIRP + Taylor",
    "L_USA_1_dotplot":           "Dot plot Fed — proyecciones SEP",
    "L_USA_2_path_fed":          "Fed Funds: mercado · analistas · sentiment",
    "L_USA_3_curvas_usa":        "Estructura temporal de tasas USA",
    "L_FX_1_g10":                "FX G10 + DXY: spots y evolución",
    "L_PA_1_corp_sector_plazo":  "Panamá corp · crédito × sector × plazo",
    "L_PA_2_soberano":           "Panamá soberano · curvas y forwards",
}


@dataclass
class SlideMessage:
    slug: str
    title: str
    proposed: str       # mensaje generado automáticamente
    edited: str | None  # versión editada por el usuario (None = usar propuesto)

    @property
    def final(self) -> str:
        return self.edited if self.edited else self.proposed


def build_all_proposed(as_of: date) -> dict[str, str]:
    """Calcula los mensajes propuestos para todas las slides del corte."""
    # imports lazy para evitar circular
    from .modelo_combinado import build_msg_l_usa_0
    from .fed_dotplot       import build_msg_l_usa_1
    from .path_fed          import build_msg_l_usa_2
    from .curvas_usa        import build_msg_l_usa_3
    from .fx_g10            import build_msg_l_fx_1
    from .panama_corp       import build_msg_l_pa_1
    from .panama_soberano   import build_msg_l_pa_2

    return {
        "L_USA_0_modelo_combinado": build_msg_l_usa_0(as_of),
        "L_USA_1_dotplot":           build_msg_l_usa_1(as_of),
        "L_USA_2_path_fed":          build_msg_l_usa_2(as_of),
        "L_USA_3_curvas_usa":        build_msg_l_usa_3(as_of),
        "L_FX_1_g10":                build_msg_l_fx_1(as_of),
        "L_PA_1_corp_sector_plazo":  build_msg_l_pa_1(as_of),
        "L_PA_2_soberano":           build_msg_l_pa_2(as_of),
    }


def save_messages_json(as_of: date, base_dir: Path | str | None = None) -> Path:
    """Persiste messages.json con propuesta + 'edited' vacío."""
    base = Path(base_dir) if base_dir else Path(f"docs/informativa/outputs/{as_of}")
    base.mkdir(parents=True, exist_ok=True)
    out = base / "messages.json"

    proposed = build_all_proposed(as_of)

    # Conserva ediciones previas si existen
    existing = {}
    if out.exists():
        try:
            existing = json.loads(out.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    blob = {
        "as_of": str(as_of),
        "slides": [
            {
                "slug": slug,
                "title": SLUG_TITLES[slug],
                "proposed": proposed[slug],
                "edited": (existing.get("slides", []) and
                           next((s.get("edited") for s in existing["slides"]
                                 if s.get("slug") == slug), None)) or None,
            }
            for slug in SLUG_ORDER if slug in proposed
        ],
    }
    out.write_text(json.dumps(blob, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    return out


def load_messages_json(as_of: date,
                      base_dir: Path | str | None = None
                      ) -> dict[str, str]:
    """Lee messages.json y devuelve {slug: final_text} (edited si existe,
    sino proposed). Si no hay JSON, regenera propuesta on-the-fly."""
    base = Path(base_dir) if base_dir else Path(f"docs/informativa/outputs/{as_of}")
    p = base / "messages.json"
    if not p.exists():
        return build_all_proposed(as_of)
    blob = json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for s in blob.get("slides", []):
        out[s["slug"]] = s.get("edited") or s.get("proposed") or ""
    return out
