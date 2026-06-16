"""Compilador del deck de la pieza informativa.

Patrón auto-descubridor: si una slide no tiene su PNG generado, se omite y
queda registrado en el resumen. Mismo estilo que Producto B.

Sprint 1 — bloque USA (3 slides):
  L_USA_1 — Dot plot SEP + evolución
  L_USA_2 — Path Fed Funds multi-fuente
  L_USA_3 — Estructura temporal (UST nominal/TIPS/breakeven/forwards 5y)

Uso:
    PYTHONPATH=src python -m tasas_mercantil.informativa.deck <as_of>
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import sys

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

SLIDE_W_IN = 13.33
SLIDE_H_IN = 7.50
BLUE = RGBColor(0x2A, 0x6F, 0xB3)
DARKBLUE = RGBColor(0x1A, 0x3A, 0x5C)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT = RGBColor(0xE8, 0xEF, 0xF7)
GREY = RGBColor(0x66, 0x66, 0x66)

DISCLAIMER = ("Documento informativo con fines analíticos. No constituye "
              "recomendación de inversión.")

# (slug, título, descripción)
USA_SLIDES = [
    ("L_USA_1_dotplot",      "Dot plot Fed — proyecciones SEP", "Sprint 1.2"),
    ("L_USA_2_path_fed",     "Fed Funds: mercado · analistas · sentiment", "Sprint 1.3"),
    ("L_USA_3_curvas_usa",   "Estructura temporal de tasas USA",           "Sprint 1.1 ✓"),
]


def _blank(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def _bg(slide, color):
    bg = slide.shapes.add_shape(1, Inches(0), Inches(0),
                                Inches(SLIDE_W_IN), Inches(SLIDE_H_IN))
    bg.fill.solid()
    bg.fill.fore_color.rgb = color
    bg.line.fill.background()


def _text(slide, left, top, w, h, text, size, color, bold=False,
          italic=False, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(Inches(left), Inches(top),
                                   Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    p.text = text
    r = p.runs[0]
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.italic = italic
    r.font.color.rgb = color


def _cover(prs, as_of):
    s = _blank(prs)
    _bg(s, BLUE)
    _text(s, 0.8, 2.3, SLIDE_W_IN - 1.6, 1.3,
          "Pieza informativa — Tasas USA", 42, WHITE, bold=True)
    _text(s, 0.8, 3.4, SLIDE_W_IN - 1.6, 0.9,
          "Estructura temporal · proyecciones Fed · expectativas",
          24, WHITE)
    _text(s, 0.8, 4.4, SLIDE_W_IN - 1.6, 0.7,
          f"Corte de análisis · {as_of.isoformat()}", 20, LIGHT)
    _text(s, 0.8, 6.5, SLIDE_W_IN - 1.6, 0.5,
          "Datos: Bloomberg · FRED · EODHD · Fed (SEP) · NY Fed (PD Survey)",
          12, LIGHT, italic=True)


def _section(prs, title, subtitle=""):
    s = _blank(prs)
    _bg(s, DARKBLUE)
    _text(s, 0.8, 2.9, SLIDE_W_IN - 1.6, 1.1, title, 32, WHITE, bold=True)
    if subtitle:
        _text(s, 0.8, 4.0, SLIDE_W_IN - 1.6, 1.2, subtitle, 17, LIGHT)


def _image(prs, png, header):
    s = _blank(prs)
    _text(s, 0.4, 0.12, SLIDE_W_IN - 0.8, 0.4, header, 14, DARKBLUE, bold=True)
    s.shapes.add_picture(str(png), Inches(0.4), Inches(0.6),
                         width=Inches(SLIDE_W_IN - 0.8))
    _text(s, 0.4, 7.15, SLIDE_W_IN - 0.8, 0.3, DISCLAIMER, 8, GREY, italic=True)


def _placeholder(prs, header, subtitle):
    s = _blank(prs)
    _text(s, 0.4, 0.12, SLIDE_W_IN - 0.8, 0.4, header, 14, DARKBLUE, bold=True)
    box = s.shapes.add_textbox(Inches(2), Inches(2.8),
                               Inches(SLIDE_W_IN - 4), Inches(2))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    p.text = f"En construcción · {subtitle}"
    p.runs[0].font.size = Pt(22)
    p.runs[0].font.color.rgb = GREY
    p.runs[0].font.italic = True


def compile_informativa(as_of: date, output_path: Path | str | None = None
                        ) -> tuple[Path, list[str], list[str]]:
    if output_path is None:
        output_path = (Path(f"docs/informativa/outputs/{as_of.isoformat()}"
                            f"/deck_informativa_usa_{as_of.isoformat()}.pptx"))
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    prs = Presentation()
    prs.slide_width = Inches(SLIDE_W_IN)
    prs.slide_height = Inches(SLIDE_H_IN)

    _cover(prs, as_of)
    _section(prs, "Bloque USA — Sprint 1",
             "L_USA_1 dot plot · L_USA_2 path multi-fuente · "
             "L_USA_3 estructura temporal")

    base = Path(f"docs/informativa/outputs/{as_of.isoformat()}")
    included, pending = [], []
    for slug, title, status in USA_SLIDES:
        png = base / f"{slug}.png"
        header = f"{title}  ·  corte {as_of}"
        if png.exists():
            _image(prs, png, header)
            included.append(slug)
        else:
            _placeholder(prs, header, status)
            pending.append(slug)

    _section(prs, "Compliance", DISCLAIMER)
    prs.save(str(output_path))
    return output_path, included, pending


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "2026-05-30"
    as_of = date.fromisoformat(arg)
    out, inc, pend = compile_informativa(as_of)
    print(f"Deck: {out}")
    print(f"Slides con PNG ({len(inc)}): {inc}")
    print(f"Slides pendientes ({len(pend)}): {pend}")
