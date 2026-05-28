#!/usr/bin/env python3
"""
Genera plantillas Bloomberg HISTORICAS para backfill del modelo predictivo.

Output: dos archivos en plantilla_bloomberg/historico/:
- BloombergHistorico_TasasMercantil_FULL.xlsx       (1985-01-01 a hoy, ~40 anos)
- BloombergHistorico_TasasMercantil_ALT_20Y.xlsx    (alternativo si el FULL se traba)

Estos no son cortes mensuales; son una SOLA pasada para poblar la serie
historica diaria que alimenta el modelo y los graficos de 12M corridos.

Diferencias vs la plantilla mensual:
- Una fila NO es un instrumento; una fila ES una fecha.
- =BDH con rango (start, end) devuelve toda la serie de una.
- Hoja por categoria de instrumento (vs todo en formato long).
- El analista corre UNA VEZ. No es recurrente.

Patron de formula:
    =BDH(ticker, "PX_LAST", FROM_DATE, TO_DATE, "Dir=V", "Dts=H", "Fill=B", "cols=2;rows=12000")

Esto desborda en una tabla de 2 columnas (fecha, valor) por instrumento.
"""
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# --------------------------------------------------------------------------- #
# Catalogo: instrumentos a bajar en histórico
# Solo cosas reales de mercado (no series macro que vendran de FRED)
# --------------------------------------------------------------------------- #

INSTRUMENTOS_HISTORICO = {
    # Fase 1 - USA - UST nominal (constant maturity)
    "UST_Nominal": [
        ("UST_1M",  "USGG1M Index",  "US Treasury 1M nominal"),
        ("UST_3M",  "USGG3M Index",  "US Treasury 3M nominal"),
        ("UST_6M",  "USGG6M Index",  "US Treasury 6M nominal"),
        ("UST_1Y",  "USGG12M Index", "US Treasury 1Y nominal"),
        ("UST_2Y",  "USGG2YR Index", "US Treasury 2Y nominal"),
        ("UST_3Y",  "USGG3YR Index", "US Treasury 3Y nominal"),
        ("UST_5Y",  "USGG5YR Index", "US Treasury 5Y nominal"),
        ("UST_7Y",  "USGG7YR Index", "US Treasury 7Y nominal"),
        ("UST_10Y", "USGG10YR Index","US Treasury 10Y nominal"),
        ("UST_20Y", "USGG20YR Index","US Treasury 20Y nominal — gap 2002-2006"),
        ("UST_30Y", "USGG30YR Index","US Treasury 30Y nominal — gap 2002-2006"),
    ],
    "TIPS_Real": [
        ("TIPS_5Y",  "USGGT05Y Index", "TIPS 5Y CMT — disponible desde 2003"),
        ("TIPS_10Y", "USGGT10Y Index", "TIPS 10Y CMT — disponible desde 2003"),
        ("TIPS_20Y", "USGGT20Y Index", "TIPS 20Y CMT — disponible desde 2004"),
        ("TIPS_30Y", "USGGT30Y Index", "TIPS 30Y CMT — disponible desde 2010"),
    ],
    "Breakevens": [
        ("BE_2Y",  "USGGBE02 Index", "US 2Y breakeven inflation"),
        ("BE_5Y",  "USGGBE05 Index", "US 5Y breakeven inflation"),
        ("BE_10Y", "USGGBE10 Index", "US 10Y breakeven inflation"),
        ("BE_30Y", "USGGBE30 Index", "US 30Y breakeven inflation"),
    ],
    "Swap_SOFR_OIS": [
        ("SOFR_OIS_2Y",  "USOSFR2 BGN Curncy",  "USD SOFR OIS 2Y - confirmar conv"),
        ("SOFR_OIS_5Y",  "USOSFR5 BGN Curncy",  "USD SOFR OIS 5Y - confirmar conv"),
        ("SOFR_OIS_10Y", "USOSFR10 BGN Curncy", "USD SOFR OIS 10Y - confirmar conv"),
        ("SOFR_OIS_30Y", "USOSFR30 BGN Curncy", "USD SOFR OIS 30Y - confirmar conv"),
    ],
    # Pre-SOFR usamos USD swap clasico (LIBOR-based) como proxy
    "Swap_USD_Clasico_LIBOR": [
        ("USSW2_LIBOR",  "USSW2 Curncy",  "USD swap 2Y LIBOR-based (pre-SOFR proxy)"),
        ("USSW5_LIBOR",  "USSW5 Curncy",  "USD swap 5Y LIBOR-based"),
        ("USSW10_LIBOR", "USSW10 Curncy", "USD swap 10Y LIBOR-based"),
        ("USSW30_LIBOR", "USSW30 Curncy", "USD swap 30Y LIBOR-based"),
    ],
    "SOFR_Money_Market": [
        ("SOFR_ON",       "SOFRRATE Index",       "SOFR overnight - desde 2018-04"),
        ("SOFR_30D_AVG",  "SOFR30A Index",        "SOFR 30-day average"),
        ("SOFR_90D_AVG",  "SOFR90A Index",        "SOFR 90-day average"),
        ("TERM_SOFR_1M",  "USOSFR1Z BGN Curncy",  "Term SOFR 1M"),
        ("TERM_SOFR_3M",  "USOSFR3Z BGN Curncy",  "Term SOFR 3M"),
        ("TERM_SOFR_6M",  "USOSFR6Z BGN Curncy",  "Term SOFR 6M"),
        ("TERM_SOFR_12M", "USOSFR12Z BGN Curncy", "Term SOFR 12M"),
    ],
    "FedFunds_Policy": [
        ("FED_FUNDS_UPPER", "FDTR Index",   "Fed Funds Target Upper Bound (post-2008)"),
        ("FED_FUNDS_LOWER", "FDFD Index",   "Fed Funds Target Lower Bound - confirmar"),
        ("FED_FUNDS_TARGET_PRE2008", "FEDFUND Index", "Fed Funds Target unico (pre-Dec-2008) - confirmar"),
        ("EFFR",            "FEDL01 Index", "Effective Fed Funds Rate"),
        ("IORB",            "FRRRIORB Index","Interest on Reserve Balances - desde 2008"),
        ("ON_RRP",          "RRPONTSY Index","Overnight Reverse Repo"),
    ],
    # Pre-SOFR: EuroDollar futures como proxy de implied path Fed Funds
    "EuroDollar_Futures_Proxy_PreSOFR": [
        ("ED_1Q", "ED1 Comdty", "EuroDollar continuous 1st quarter (pre-SOFR proxy)"),
        ("ED_2Q", "ED2 Comdty", "EuroDollar continuous 2nd"),
        ("ED_3Q", "ED3 Comdty", "EuroDollar continuous 3rd"),
        ("ED_4Q", "ED4 Comdty", "EuroDollar continuous 4th"),
        ("ED_5Q", "ED5 Comdty", "EuroDollar continuous 5th"),
        ("ED_6Q", "ED6 Comdty", "EuroDollar continuous 6th"),
        ("ED_7Q", "ED7 Comdty", "EuroDollar continuous 7th"),
        ("ED_8Q", "ED8 Comdty", "EuroDollar continuous 8th"),
    ],
    # SOFR futures (SR3) — disponibles desde 2018-05
    "SR3_SOFR_Futures": [
        (f"SR3_{n}Q", f"SFR{n} Comdty", f"SOFR future month {n}") for n in range(1, 9)
    ],
}


# --------------------------------------------------------------------------- #
# Estilos
# --------------------------------------------------------------------------- #
HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
INPUT_FILL = PatternFill("solid", fgColor="E8F4FF")
FORMULA_FILL = PatternFill("solid", fgColor="F4F4F4")
WARN_FILL = PatternFill("solid", fgColor="FFE6CC")


def style_header(cell):
    cell.fill = HEADER_FILL
    cell.font = HEADER_FONT
    cell.alignment = Alignment(horizontal="left", vertical="center")


# --------------------------------------------------------------------------- #
# Hojas
# --------------------------------------------------------------------------- #
def sheet_instrucciones(wb, from_date: str, to_label: str):
    ws = wb.create_sheet("00_Instrucciones")
    rows = [
        (f"Plantilla Bloomberg HISTORICA — {from_date} a {to_label}", "header"),
        ("", "blank"),
        ("Que es esto", "h2"),
        ("Carga UNICA (una sola vez) de la serie historica diaria de tasas, swaps, TIPS, breakevens y futuros.", "body"),
        ("Esto alimenta el backtest del modelo predictivo (1985+) y los graficos de 12M corridos de cada corte.", "body"),
        ("NO es una plantilla recurrente — se corre una vez y se devuelve.", "body"),
        ("", "blank"),
        ("Como usarlo (paso a paso)", "h2"),
        ("1. Abrir el archivo en Excel con Bloomberg add-in activo.", "body"),
        ("2. En la hoja '01_Parametros', las fechas FROM_DATE y TO_DATE YA estan fijadas.", "body"),
        ("   NO usar =TODAY() — el TO_DATE es fecha literal del cierre del mes corriente.", "body"),
        ("3. Llenar ANALISTA (B5) y FECHA_CARGA (B6, fecha en que corres Bloomberg).", "body"),
        ("4. CADA HOJA DE DATOS tiene una formula =BDH en celda A4 con rango (FROM_DATE, TO_DATE).", "body"),
        ("   La formula se desborda automaticamente como tabla de 2 columnas (fecha, valor) por instrumento.", "body"),
        ("   Esperar a que Bloomberg complete TODAS las series (puede tomar 5-15 minutos).", "body"),
        ("5. CRITICO — Si el archivo se TRABA o no termina:", "body"),
        ("   - Cerrar Excel sin guardar.", "body"),
        ("   - Abrir el archivo ALTERNATIVO de 20 anos.", "body"),
        ("   - Repetir el proceso ahi (rango mas corto = mas rapido).", "body"),
        ("6. CRITICO — Paste Special -> Values en cada hoja de datos:", "body"),
        ("   - Ctrl+A (toda la hoja) -> Ctrl+C -> Edit -> Paste Special -> Values.", "body"),
        ("   - Esto congela los valores. Sin este paso, al reabrir sin Bloomberg se ven #N/A.", "body"),
        ("7. Escribir FECHA_GUARDADO_VALUES (B7).", "body"),
        ("8. Guardar el archivo con el sufijo correspondiente (FULL o ALT_20Y).", "body"),
        ("9. Devolver: subir a github.com/andresborrerom/credito_Panama branch", "body"),
        ("   claude/tasas-mercantil-report-Q8sFt, carpeta", "body"),
        ("   ProyectoTasasMercantil/plantilla_bloomberg/historico/. O por correo.", "body"),
        ("", "blank"),
        ("Notas tecnicas", "h2"),
        ("- Las series con datos faltantes pre-fecha-de-existencia (TIPS antes de 2003, SOFR antes de 2018)", "body"),
        ("  apareceran vacias en las primeras filas. Eso es esperado, no es error.", "body"),
        ("- UST 20Y y 30Y tienen un GAP entre 2002-2006 cuando Treasury suspendio la emision.", "body"),
        ("  Bloomberg devolvera NaN en ese rango. Tambien esperado.", "body"),
        ("- Si algun ticker da #N/A Invalid Security, anotarlo en la hoja '05_Notas_Analista' con", "body"),
        ("  sugerencia del ticker correcto.", "body"),
        ("- Recomendacion: cerrar el resto de aplicaciones pesadas mientras corre. Bloomberg consume RAM.", "body"),
        ("", "blank"),
        ("Tiempo estimado", "h2"),
        ("FULL (40 anos): 10-20 minutos de carga + 2 min de Paste Values. Tamaño final ~10-20 MB.", "body"),
        ("ALT 20Y: 5-10 minutos. Tamaño final ~5-10 MB.", "body"),
    ]
    for i, (text, kind) in enumerate(rows, start=1):
        cell = ws.cell(row=i, column=1, value=text)
        if kind == "header":
            cell.font = Font(bold=True, size=16, color="1F3A5F")
        elif kind == "h2":
            cell.font = Font(bold=True, size=12, color="1F3A5F")
        elif kind == "body":
            cell.font = Font(size=10)
            cell.alignment = Alignment(wrap_text=True)
    ws.column_dimensions["A"].width = 130


def sheet_parametros(wb, from_date: str, to_date_text: str):
    ws = wb.create_sheet("01_Parametros")
    ws.cell(row=1, column=1, value="Parametros del backfill historico").font = Font(bold=True, size=14, color="1F3A5F")

    headers = ["Parametro", "Valor", "Tipo", "Descripcion"]
    for j, h in enumerate(headers, start=1):
        c = ws.cell(row=2, column=j, value=h)
        style_header(c)

    # NO usar =TODAY() — fechas literales para evitar el bug heredado de SAA.
    rows = [
        ("FROM_DATE",              from_date,    "fixed", "Inicio de la serie historica — literal, NO formula", "yyyy-mm-dd"),
        ("TO_DATE",                to_date_text, "fixed", "Fin de la serie historica — literal, ajustar antes de correr",  "yyyy-mm-dd"),
        ("ANALISTA",               None,         "input", "Nombre del analista que corre la plantilla",        None),
        ("FECHA_CARGA",            None,         "input", "Fecha de carga — escribir a mano (NO =TODAY())",     "yyyy-mm-dd"),
        ("FECHA_GUARDADO_VALUES",  None,         "input", "Fecha del Paste Special -> Values — manual",         "yyyy-mm-dd"),
        ("VERSION_PLANTILLA",      "FULL o ALT_20Y", "fixed", "FULL = 1985-presente, ALT_20Y = ~20 anos", None),
        ("NOTAS",                  None,         "input", "Observaciones, tickers fallidos, etc.",             None),
    ]
    for i, (n, v, k, d, fmt) in enumerate(rows, start=3):
        ws.cell(row=i, column=1, value=n).font = Font(bold=True)
        cell = ws.cell(row=i, column=2, value=v)
        ws.cell(row=i, column=3, value=k)
        ws.cell(row=i, column=4, value=d)
        if k == "input":
            cell.fill = INPUT_FILL
        else:
            cell.fill = FORMULA_FILL
        if fmt:
            cell.number_format = fmt

    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 26
    ws.column_dimensions["C"].width = 12
    ws.column_dimensions["D"].width = 70


def sheet_datos_categoria(wb, categoria: str, instrumentos: list, row_buffer: int):
    """Una hoja por categoria.

    Layout:
    - Fila 1: titulo
    - Fila 2: notas
    - Fila 3: headers (instrument, ticker, descripcion)
    - Fila 4: cada instrumento ocupa 2 columnas (date, value) con =BDH spilled.

    `row_buffer` es el "rows=N" del =BDH (debe cubrir el periodo). Para 40 anos
    diarios ≈ 10,400 filas habiles. Buffer 12000 esta bien.
    """
    ws = wb.create_sheet(categoria[:31])  # max 31 chars sheet name
    ws.cell(row=1, column=1, value=f"Categoria: {categoria}").font = Font(bold=True, size=12, color="1F3A5F")
    ws.cell(row=2, column=1, value=(
        f"Cada instrumento ocupa 2 columnas (fecha, valor). "
        f"La formula =BDH en fila 4 se desborda hacia abajo automaticamente."
    )).font = Font(size=9, italic=True, color="666666")

    # Headers en fila 3, 2 columnas por instrumento
    col = 1
    for nombre, ticker, desc in instrumentos:
        c1 = ws.cell(row=3, column=col, value=f"{nombre} — fecha")
        c2 = ws.cell(row=3, column=col + 1, value=f"{nombre} — valor")
        style_header(c1)
        style_header(c2)
        # Tooltip-style notes en fila 2.5 (usamos comentario)
        c1.comment = None  # podriamos agregar comments
        # Formula BDH en fila 4 col actual (la 1a de las 2)
        # Dts=S (Shown) — IMPORTANTE: NO usar Dts=H que oculta la columna de
        # fechas. Es la misma leccion que SAA aprendio (ver
        # 12_DATA_AUDIT_FINDINGS.md). Sin las fechas visibles, el parser no
        # puede alinear la serie y el analista no puede sanity-check.
        formula = (
            f'=BDH("{ticker}","PX_LAST",'
            f"'01_Parametros'!$B$3,'01_Parametros'!$B$4,"
            f'"Dir=V","Dts=S","Fill=B","cols=2;rows={row_buffer}")'
        )
        ws.cell(row=4, column=col, value=formula).fill = FORMULA_FILL
        # Nota / descripcion en fila 5
        ws.cell(row=5, column=col, value=f"Ticker: {ticker}").font = Font(size=8, color="666666")
        ws.cell(row=5, column=col + 1, value=desc).font = Font(size=8, color="666666")
        # Width
        ws.column_dimensions[get_column_letter(col)].width = 13
        ws.column_dimensions[get_column_letter(col + 1)].width = 12
        col += 2

    ws.freeze_panes = "A6"


def sheet_notas(wb):
    ws = wb.create_sheet("05_Notas_Analista")
    ws.cell(row=1, column=1, value="Notas del analista").font = Font(bold=True, size=14, color="1F3A5F")
    ws.cell(row=3, column=1, value=(
        "Tickers que fallaron, series con gaps inesperados, sugerencias, observaciones de carga."
    )).font = Font(italic=True)
    ws.cell(row=5, column=1, value="Tickers fallidos / corregidos").font = Font(bold=True)
    for i in range(6, 20):
        ws.cell(row=i, column=1, value="").fill = INPUT_FILL
        ws.cell(row=i, column=2, value="").fill = INPUT_FILL
    ws.cell(row=21, column=1, value="Series con datos faltantes inesperados").font = Font(bold=True)
    for i in range(22, 30):
        ws.cell(row=i, column=1, value="").fill = INPUT_FILL
    ws.cell(row=31, column=1, value="Observaciones de carga").font = Font(bold=True)
    for i in range(32, 40):
        ws.cell(row=i, column=1, value="").fill = INPUT_FILL
    ws.column_dimensions["A"].width = 50
    ws.column_dimensions["B"].width = 60


def sheet_envio(wb):
    ws = wb.create_sheet("99_Envio")
    rows = [
        ("Como devolver este archivo", "header"),
        ("", "blank"),
        ("OPCION 1 — Recomendada — Upload directo a GitHub (web)", "h2"),
        ("1. Guardar con sufijo FULL o ALT_20Y segun corresponda.", "body"),
        ("2. Ir a github.com/andresborrerom/credito_Panama, branch claude/tasas-mercantil-report-Q8sFt.", "body"),
        ("3. Navegar a ProyectoTasasMercantil/plantilla_bloomberg/historico/.", "body"),
        ("4. Add file -> Upload files -> arrastrar el xlsx.", "body"),
        ("5. Commit message: 'historico: carga Bloomberg <FULL|ALT_20Y> por <analista>'.", "body"),
        ("", "blank"),
        ("OPCION 2 — Correo", "h2"),
        ("Adjuntar y mandar a Andres. Asunto: 'Tasas Mercantil — Carga historica Bloomberg <FULL|ALT_20Y>'.", "body"),
    ]
    for i, (text, kind) in enumerate(rows, start=1):
        cell = ws.cell(row=i, column=1, value=text)
        if kind == "header":
            cell.font = Font(bold=True, size=16, color="1F3A5F")
        elif kind == "h2":
            cell.font = Font(bold=True, size=12, color="1F3A5F")
        elif kind == "body":
            cell.font = Font(size=10)
    ws.column_dimensions["A"].width = 110


# --------------------------------------------------------------------------- #
# Main builder
# --------------------------------------------------------------------------- #
def build_template(from_date: str, to_date_text: str, out_path: Path, row_buffer: int):
    """Construye una plantilla con un rango especifico."""
    wb = Workbook()
    wb.remove(wb.active)

    sheet_instrucciones(wb, from_date, to_date_text)
    sheet_parametros(wb, from_date, to_date_text)
    for cat, instruments in INSTRUMENTOS_HISTORICO.items():
        sheet_datos_categoria(wb, cat, instruments, row_buffer=row_buffer)
    sheet_notas(wb)
    sheet_envio(wb)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    n_inst = sum(len(v) for v in INSTRUMENTOS_HISTORICO.values())
    print(f"[OK] {out_path}  ({n_inst} instrumentos × rango {from_date} → {to_date_text})")


def main():
    base = Path("/home/user/credito_Panama/ProyectoTasasMercantil/plantilla_bloomberg/historico")

    # FULL: 1985-presente. ~40 anos * 252 dias habiles = ~10,080 filas. Buffer 12000.
    build_template(
        from_date="1985-01-01",
        to_date_text="2026-05-29",
        out_path=base / "BloombergHistorico_TasasMercantil_FULL.xlsx",
        row_buffer=12000,
    )

    # ALT 20Y: 2006-presente. ~20 anos * 252 = ~5,040 filas. Buffer 6000.
    build_template(
        from_date="2006-01-01",
        to_date_text="2026-05-29",
        out_path=base / "BloombergHistorico_TasasMercantil_ALT_20Y.xlsx",
        row_buffer=6000,
    )


if __name__ == "__main__":
    main()
