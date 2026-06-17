"""Compilador del deck Fase 1 USA — junta las 8 láminas + portada en .pptx.

Orden canónico:
  Slide 0  — Portada (título, fecha de corte, autor, modelo version)
  Slide 1  — L1 Mensajes clave del mes
  Slide 2  — L2 Política monetaria Fed
  Slide 3  — L3 Tasas de mercado (SOFR)
  Slide 4  — L4 Curva UST 3 cortes
  Slide 5  — L5 Expectativas Fed (modelo Mercantil)
  Slide 6  — L6 Calendario USA próximos 30-60d
  Slide 7  — L7 Destacados del mes (news + sorpresas)
  Slide 8  — L8 Lectura del analista

Cada slide es un PNG full-bleed sobre canvas 16:9.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor


SLIDE_W_IN = 13.33  # 16:9 widescreen
SLIDE_H_IN = 7.50


@dataclass
class DeckSlide:
    order: int
    label: str
    title: str
    png_relpath: str


def _build_slide_list(as_of: date) -> list[DeckSlide]:
    d = as_of.isoformat()
    base = "docs/producto_a/outputs"
    return [
        DeckSlide(1, "L1", "Mensajes clave del mes",
                   f"{base}/mensajes_clave_{d}.png"),
        DeckSlide(2, "L2", "Política monetaria Fed",
                   f"{base}/politica_monetaria_fed_{d}.png"),
        DeckSlide(3, "L3", "Tasas de mercado (SOFR)",
                   f"{base}/tasas_mercado_usa_{d}.png"),
        DeckSlide(4, "L4", "Curva UST — 3 cortes",
                   f"{base}/curva_ust_3cortes_{d}.png"),
        DeckSlide(5, "L5", "Expectativas Fed (modelo Mercantil)",
                   f"{base}/expectativas_fed_{d}.png"),
        DeckSlide(6, "L6", "Calendario USA",
                   f"{base}/calendario_usa_{d}.png"),
        DeckSlide(7, "L7", "Destacados del mes",
                   f"{base}/destacados_usa_{d}.png"),
        DeckSlide(8, "L8", "Lectura del analista",
                   f"{base}/lectura_analista_{d}.png"),
    ]


def _add_cover_slide(prs: Presentation, as_of: date):
    """Portada: título + corte + autor."""
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)

    # Fondo azul
    bg = slide.shapes.add_shape(
        1,  # rectangle
        Inches(0), Inches(0), Inches(SLIDE_W_IN), Inches(SLIDE_H_IN),
    )
    bg.fill.solid()
    bg.fill.fore_color.rgb = RGBColor(0x2A, 0x6F, 0xB3)
    bg.line.fill.background()

    # Título
    title_box = slide.shapes.add_textbox(
        Inches(0.8), Inches(2.5),
        Inches(SLIDE_W_IN - 1.6), Inches(1.2))
    tf = title_box.text_frame
    p = tf.paragraphs[0]
    p.text = "Reporte Tasas Mercantil"
    p.runs[0].font.size = Pt(44)
    p.runs[0].font.bold = True
    p.runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    sub_box = slide.shapes.add_textbox(
        Inches(0.8), Inches(3.7),
        Inches(SLIDE_W_IN - 1.6), Inches(0.7))
    tf = sub_box.text_frame
    p = tf.paragraphs[0]
    p.text = f"Fase 1 — USA  ·  Corte {as_of.isoformat()}"
    p.runs[0].font.size = Pt(24)
    p.runs[0].font.color.rgb = RGBColor(0xE8, 0xEF, 0xF7)

    foot_box = slide.shapes.add_textbox(
        Inches(0.8), Inches(6.5),
        Inches(SLIDE_W_IN - 1.6), Inches(0.5))
    tf = foot_box.text_frame
    p = tf.paragraphs[0]
    p.text = "Modelo Mercantil v0.3.0  ·  Datos: Bloomberg + FRED + EODHD"
    p.runs[0].font.size = Pt(12)
    p.runs[0].font.italic = True
    p.runs[0].font.color.rgb = RGBColor(0xE8, 0xEF, 0xF7)


def _add_image_slide(prs: Presentation, png_path: Path, title: str):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)

    # Imagen ocupando casi todo el slide (deja header chico)
    img_top = Inches(0.5)
    img_left = Inches(0.4)
    img_w = Inches(SLIDE_W_IN - 0.8)
    slide.shapes.add_picture(str(png_path), img_left, img_top, width=img_w)


def compile_deck_fase1_usa(as_of: date,
                            output_path: Path | str | None = None
                            ) -> Path:
    """Compila las 8 láminas + portada en un .pptx 16:9.

    Las láminas deben existir como PNGs en docs/producto_a/outputs/.
    """
    if output_path is None:
        output_path = Path(f"docs/producto_a/outputs/"
                             f"deck_fase1_usa_{as_of.isoformat()}.pptx")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    prs = Presentation()
    prs.slide_width = Inches(SLIDE_W_IN)
    prs.slide_height = Inches(SLIDE_H_IN)

    _add_cover_slide(prs, as_of)

    slides = _build_slide_list(as_of)
    missing = []
    for s in slides:
        p = Path(s.png_relpath)
        if not p.exists():
            missing.append(s.label)
            continue
        _add_image_slide(prs, p, f"{s.label} · {s.title}")

    prs.save(str(output_path))
    return output_path, missing


if __name__ == "__main__":
    from datetime import date as _date
    out, missing = compile_deck_fase1_usa(_date(2026, 6, 15))
    print(f"✓ Deck: {out}  ({out.stat().st_size // 1024} KB)")
    if missing:
        print(f"⚠ Slides faltantes: {missing}")
