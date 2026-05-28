#!/usr/bin/env python3
"""
Genera la plantilla Bloomberg para el reporte mensual de tasas Mercantil.

Output: ProyectoTasasMercantil/plantilla_bloomberg/BloombergTemplate_TasasMercantil.xlsx

El archivo se entrega al analista cada mes. El analista ajusta la fecha AS_OF
en la hoja 01_Parametros, espera que las formulas =BDH/=BDP resuelvan, y
devuelve el .xlsx con valores cargados.

Convencion de formulas Bloomberg:
- BDH(ticker, field, start, end, "Dir=H", "Fill=B") = historico
- BDP(ticker, field) = spot live (PX_LAST)
- Para un punto a fecha pasada usamos BDH con start=end=fecha y envuelto en INDEX(...,1,2)
  para devolver solo el valor (la primera columna es la fecha).

Si el cliente esta en Excel 365 con dynamic arrays, las formulas se desbordan
automaticamente. Si esta en Excel 2019 o anterior, hay que Ctrl+Shift+Enter.
La nota va en la hoja 00_Instrucciones.
"""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

# --------------------------------------------------------------------------- #
# Catalogo de instrumentos
# --------------------------------------------------------------------------- #

INSTRUMENTOS = [
    # categoria, region, instrument, tenor_label, tenor_years, ticker, field, unit, nota
    # Fase 1 - USA - Politica monetaria
    ("policy", "US", "FED_FUNDS_UPPER", "—", 0.0, "FDTR Index", "PX_LAST", "percent", "Fed Funds Target Upper Bound"),
    ("policy", "US", "FED_FUNDS_LOWER", "—", 0.0, "FDFD Index", "PX_LAST", "percent", "Fed Funds Target Lower Bound — confirmar ticker"),
    ("policy", "US", "EFFR", "ON", 0.0, "FEDL01 Index", "PX_LAST", "percent", "Effective Fed Funds Rate"),
    ("policy", "US", "IORB", "—", 0.0, "FRRRIORB Index", "PX_LAST", "percent", "Interest on Reserve Balances"),
    ("policy", "US", "ON_RRP", "ON", 0.0, "RRPONTSY Index", "PX_LAST", "percent", "Overnight Reverse Repo"),

    # Fase 1 - USA - SOFR (term)
    ("money_market", "US", "SOFR_ON", "ON", 0.003, "SOFRRATE Index", "PX_LAST", "percent", "SOFR overnight"),
    ("money_market", "US", "SOFR_1M_AVG", "1M_AVG", 0.083, "SOFR30A Index", "PX_LAST", "percent", "SOFR 30-day average"),
    ("money_market", "US", "SOFR_3M_AVG", "3M_AVG", 0.25, "SOFR90A Index", "PX_LAST", "percent", "SOFR 90-day average"),
    ("money_market", "US", "TERM_SOFR_1M", "1M", 0.083, "USOSFR1Z BGN Curncy", "PX_LAST", "percent", "Term SOFR 1M - CME"),
    ("money_market", "US", "TERM_SOFR_3M", "3M", 0.25, "USOSFR3Z BGN Curncy", "PX_LAST", "percent", "Term SOFR 3M - CME"),
    ("money_market", "US", "TERM_SOFR_6M", "6M", 0.5, "USOSFR6Z BGN Curncy", "PX_LAST", "percent", "Term SOFR 6M - CME"),
    ("money_market", "US", "TERM_SOFR_12M", "12M", 1.0, "USOSFR12Z BGN Curncy", "PX_LAST", "percent", "Term SOFR 12M - CME"),

    # Fase 1 - USA - UST curve
    ("yield_curve", "US", "UST", "1M", 0.083, "USGG1M Index", "PX_LAST", "percent", "US Treasury 1M"),
    ("yield_curve", "US", "UST", "3M", 0.25, "USGG3M Index", "PX_LAST", "percent", "US Treasury 3M"),
    ("yield_curve", "US", "UST", "6M", 0.5, "USGG6M Index", "PX_LAST", "percent", "US Treasury 6M"),
    ("yield_curve", "US", "UST", "1Y", 1.0, "USGG12M Index", "PX_LAST", "percent", "US Treasury 1Y"),
    ("yield_curve", "US", "UST", "2Y", 2.0, "USGG2YR Index", "PX_LAST", "percent", "US Treasury 2Y"),
    ("yield_curve", "US", "UST", "3Y", 3.0, "USGG3YR Index", "PX_LAST", "percent", "US Treasury 3Y"),
    ("yield_curve", "US", "UST", "5Y", 5.0, "USGG5YR Index", "PX_LAST", "percent", "US Treasury 5Y"),
    ("yield_curve", "US", "UST", "7Y", 7.0, "USGG7YR Index", "PX_LAST", "percent", "US Treasury 7Y"),
    ("yield_curve", "US", "UST", "10Y", 10.0, "USGG10YR Index", "PX_LAST", "percent", "US Treasury 10Y"),
    ("yield_curve", "US", "UST", "20Y", 20.0, "USGG20YR Index", "PX_LAST", "percent", "US Treasury 20Y"),
    ("yield_curve", "US", "UST", "30Y", 30.0, "USGG30YR Index", "PX_LAST", "percent", "US Treasury 30Y"),

    # Fase 2 - Global - Politica monetaria
    ("policy", "EU", "ECB_DFR", "—", 0.0, "EURR002W Index", "PX_LAST", "percent", "ECB Deposit Facility Rate"),
    ("policy", "EU", "ECB_MRO", "—", 0.0, "EURMR1WI Index", "PX_LAST", "percent", "ECB Main Refi Operations — confirmar ticker"),
    ("policy", "GB", "BOE_BANK_RATE", "—", 0.0, "UKBRBASE Index", "PX_LAST", "percent", "BoE Bank Rate"),
    ("policy", "JP", "BOJ_POLICY", "—", 0.0, "BOJDPBAL Index", "PX_LAST", "percent", "BoJ policy rate"),
    ("policy", "CN", "PBOC_7D_RR", "—", 0.0, "CHRR7TR Index", "PX_LAST", "percent", "PBoC 7-day reverse repo — confirmar"),
    ("policy", "BR", "SELIC_META", "—", 0.0, "BZSTSETA Index", "PX_LAST", "percent", "Selic target"),
    ("policy", "MX", "BANXICO_TASA", "—", 0.0, "MXONBR Index", "PX_LAST", "percent", "Banxico target"),
    ("policy", "CO", "BANREP_TASA", "—", 0.0, "COBR Index", "PX_LAST", "percent", "BanRep target"),

    # Fase 2 - Global - Curvas 10Y
    ("yield_curve", "DE", "BUND", "10Y", 10.0, "GDBR10 Index", "PX_LAST", "percent", "Germany Bund 10Y"),
    ("yield_curve", "GB", "GILT", "10Y", 10.0, "GUKG10 Index", "PX_LAST", "percent", "UK Gilt 10Y"),
    ("yield_curve", "JP", "JGB", "10Y", 10.0, "GJGB10 Index", "PX_LAST", "percent", "Japan JGB 10Y"),
    ("yield_curve", "BR", "BR_GOV", "10Y", 10.0, "GEBR10Y Index", "PX_LAST", "percent", "Brazil 10Y — confirmar"),
    ("yield_curve", "MX", "MX_MBONO", "10Y", 10.0, "GMXN10YR Index", "PX_LAST", "percent", "Mexico MBONO 10Y — confirmar"),
    ("yield_curve", "CO", "CO_TES", "10Y", 10.0, "COGR10Y Index", "PX_LAST", "percent", "Colombia TES 10Y — confirmar"),

    # Fase 2 - FX
    ("fx", "—", "EURUSD", "SPOT", 0.0, "EURUSD Curncy", "PX_LAST", "rate", "EUR/USD spot"),
    ("fx", "—", "GBPUSD", "SPOT", 0.0, "GBPUSD Curncy", "PX_LAST", "rate", "GBP/USD spot"),
    ("fx", "—", "USDJPY", "SPOT", 0.0, "USDJPY Curncy", "PX_LAST", "rate", "USD/JPY spot"),
    ("fx", "—", "USDCNY", "SPOT", 0.0, "USDCNY Curncy", "PX_LAST", "rate", "USD/CNY spot"),
    ("fx", "—", "USDBRL", "SPOT", 0.0, "USDBRL Curncy", "PX_LAST", "rate", "USD/BRL spot"),
    ("fx", "—", "USDMXN", "SPOT", 0.0, "USDMXN Curncy", "PX_LAST", "rate", "USD/MXN spot"),
    ("fx", "—", "USDCOP", "SPOT", 0.0, "USDCOP Curncy", "PX_LAST", "rate", "USD/COP spot"),
    ("fx", "—", "USDCLP", "SPOT", 0.0, "USDCLP Curncy", "PX_LAST", "rate", "USD/CLP spot"),
    ("fx", "—", "DXY", "SPOT", 0.0, "DXY Curncy", "PX_LAST", "index", "Dollar Index"),

    # Fase 2 - EMBI / EM credit
    ("credit_index", "EM", "EMBI_GLOBAL_SPRD", "ALL", 0.0, "JPEIDIVR Index", "PX_LAST", "bps", "EMBI Global Diversified — confirmar"),
    ("credit_index", "LATAM", "EMBI_LATAM_SPRD", "ALL", 0.0, "JPEMLAT Index", "PX_LAST", "bps", "EMBI Latam — confirmar"),
    ("credit_index", "PA", "EMBI_PANAMA_SPRD", "ALL", 0.0, "JPGCPANS Index", "PX_LAST", "bps", "EMBI Panama spread — confirmar"),
    ("credit_index", "VE", "EMBI_VEN_SPRD", "ALL", 0.0, "JPGCVENS Index", "PX_LAST", "bps", "EMBI Venezuela spread — confirmar"),

    # Capitulo CORP - ICE BofA indices USA (IG)
    ("credit_index", "US", "ICE_C0A0_YIELD", "ALL", 0.0, "C0A0 Index", "INDEX_YIELD_TO_WORST", "percent", "ICE BofA US Corporate Master YTW"),
    ("credit_index", "US", "ICE_C0A0_OAS", "ALL", 0.0, "C0A0 Index", "OAS_SPREAD_BID", "bps", "ICE BofA US Corp Master OAS"),
    ("credit_index", "US", "ICE_C0A1_AAA_OAS", "ALL", 0.0, "C0A1 Index", "OAS_SPREAD_BID", "bps", "ICE BofA US Corp AAA OAS"),
    ("credit_index", "US", "ICE_C0A2_AA_OAS", "ALL", 0.0, "C0A2 Index", "OAS_SPREAD_BID", "bps", "ICE BofA US Corp AA OAS"),
    ("credit_index", "US", "ICE_C0A3_A_OAS", "ALL", 0.0, "C0A3 Index", "OAS_SPREAD_BID", "bps", "ICE BofA US Corp A OAS"),
    ("credit_index", "US", "ICE_C0A4_BBB_OAS", "ALL", 0.0, "C0A4 Index", "OAS_SPREAD_BID", "bps", "ICE BofA US Corp BBB OAS"),

    # Capitulo CORP - ICE BofA indices USA (HY)
    ("credit_index", "US", "ICE_H0A0_HY_YIELD", "ALL", 0.0, "H0A0 Index", "INDEX_YIELD_TO_WORST", "percent", "ICE BofA US HY Master YTW"),
    ("credit_index", "US", "ICE_H0A0_HY_OAS", "ALL", 0.0, "H0A0 Index", "OAS_SPREAD_BID", "bps", "ICE BofA US HY Master OAS"),
    ("credit_index", "US", "ICE_H0A1_BB_OAS", "ALL", 0.0, "H0A1 Index", "OAS_SPREAD_BID", "bps", "ICE BofA US HY BB OAS"),
    ("credit_index", "US", "ICE_H0A2_B_OAS", "ALL", 0.0, "H0A2 Index", "OAS_SPREAD_BID", "bps", "ICE BofA US HY Single-B OAS"),
    ("credit_index", "US", "ICE_H0A3_CCC_OAS", "ALL", 0.0, "H0A3 Index", "OAS_SPREAD_BID", "bps", "ICE BofA US HY CCC OAS"),

    # Capitulo CORP - EM USD Corp (CEMBI)
    ("credit_index", "EM", "CEMBI_BROAD_SPRD", "ALL", 0.0, "JPCBBRDF Index", "PX_LAST", "bps", "CEMBI Broad Diversified spread — confirmar"),
    ("credit_index", "LATAM", "CEMBI_LATAM_SPRD", "ALL", 0.0, "JPCBLATS Index", "PX_LAST", "bps", "CEMBI Latam spread — confirmar"),

    # Fase 5 - Venezuela
    ("fx", "VE", "USDVES_OFICIAL", "SPOT", 0.0, "USDVES Curncy", "PX_LAST", "rate", "USD/VES oficial BCV — si BBG lo tiene"),
    # USDVES paralelo NO viene por Bloomberg — se llena por scraper aparte.
]

# Strip de SOFR futures: rolling continuous front 8 quarters
SOFR_FUTURES = [
    (f"SFR{n} Comdty", f"SOFR future month {n}") for n in range(1, 9)
]

# --------------------------------------------------------------------------- #
# Estilos
# --------------------------------------------------------------------------- #
HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
PARAM_FILL = PatternFill("solid", fgColor="FFF4CE")
INPUT_FILL = PatternFill("solid", fgColor="E8F4FF")
FORMULA_FILL = PatternFill("solid", fgColor="F4F4F4")
THIN = Side(border_style="thin", color="999999")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def style_header(cell):
    cell.fill = HEADER_FILL
    cell.font = HEADER_FONT
    cell.alignment = Alignment(horizontal="left", vertical="center")
    cell.border = BORDER


def auto_width(ws, max_width=60):
    for col in ws.columns:
        col = list(col)
        if not col:
            continue
        letter = get_column_letter(col[0].column)
        length = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[letter].width = min(max(length + 2, 12), max_width)


# --------------------------------------------------------------------------- #
# Hoja: 00_Instrucciones
# --------------------------------------------------------------------------- #
def sheet_instrucciones(wb):
    ws = wb.create_sheet("00_Instrucciones")
    rows = [
        ("Plantilla Bloomberg — Reporte Mensual de Tasas Mercantil", "header"),
        ("", "blank"),
        ("Que es esto", "h2"),
        ("Plantilla que se corre cada mes para extraer datos de Bloomberg al cierre del ultimo dia habil.", "body"),
        ("Output: este mismo archivo con celdas resueltas (valores en lugar de #N/A).", "body"),
        ("", "blank"),
        ("Como usarlo (3 pasos)", "h2"),
        ("1. Abrir el archivo en Excel con Bloomberg add-in activo.", "body"),
        ("2. Ir a la hoja '01_Parametros' y EDITAR la celda B3 (AS_OF) al ultimo dia habil del mes a reportar.", "body"),
        ("   El resto de fechas (mes anterior, cierre año anterior, inicio 12M) se calculan solas.", "body"),
        ("3. Esperar a que las formulas resuelvan (puede tomar 30-90 segundos en la primera carga).", "body"),
        ("4. Verificar que NO haya celdas '#N/A Requesting Data' visibles. Si las hay:", "body"),
        ("   - Revisar conexion Bloomberg.", "body"),
        ("   - Si un ticker especifico esta marcado 'confirmar ticker' en la columna 'nota', es posible que ese ticker", "body"),
        ("     en particular requiera ajuste. Avisar a Andres/Camilo si pasa esto.", "body"),
        ("5. Ir a la hoja '04_FedWatch' y completar la tabla MANUALMENTE con paste desde la pantalla WIRP.", "body"),
        ("6. Llenar la hoja '05_Notas_Analista' con cualquier anomalia o cambio de contexto observado.", "body"),
        ("7. Guardar el archivo con el nombre: BloombergTemplate_TasasMercantil_<YYYY-MM>.xlsx", "body"),
        ("8. Devolverlo por correo o subirlo directamente a GitHub (instrucciones en hoja '99_Envio').", "body"),
        ("", "blank"),
        ("Notas tecnicas", "h2"),
        ("- Las formulas BDH devuelven valores con fill backward: si la fecha cae feriado, toma el dia habil anterior.", "body"),
        ("- En Excel 365 (dynamic arrays) las formulas funcionan tal cual.", "body"),
        ("- En Excel 2019 o anterior puede que tengas que entrar en cada celda con formula y hacer Ctrl+Shift+Enter.", "body"),
        ("- Los tickers marcados con '— confirmar' son inferencias del que armo la plantilla; si Bloomberg los rechaza,", "body"),
        ("  el analista debe sugerir el ticker correcto y marcarlo en '05_Notas_Analista'.", "body"),
        ("", "blank"),
        ("Que NO viene por aqui (no perder tiempo buscandolo)", "h2"),
        ("- Tipo de cambio bolivar paralelo Venezuela: lo extraemos via scraper publico, no Bloomberg.", "body"),
        ("- Probabilidades FedWatch implicitas: van en hoja '04_FedWatch' como paste manual desde WIRP.", "body"),
        ("- Dot plot SEP de la Fed: se actualiza solo 4 veces al año, lo cargamos nosotros tras cada FOMC.", "body"),
        ("- Datos internos del libro del banco: fuera del alcance de esta plantilla (ver docs del proyecto).", "body"),
        ("", "blank"),
        ("Tiempo estimado de carga", "h2"),
        ("Primera vez: 30-90 segundos. En reaperturas con cache: <10 segundos.", "body"),
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


# --------------------------------------------------------------------------- #
# Hoja: 01_Parametros
# --------------------------------------------------------------------------- #
def sheet_parametros(wb):
    ws = wb.create_sheet("01_Parametros")

    ws.cell(row=1, column=1, value="Parametros del corte").font = Font(bold=True, size=14, color="1F3A5F")

    fields = [
        ("MES_REPORTE", '="YYYY-MM del corte (se calcula a partir de AS_OF)"', "auto", "ej: 2026-05", "calc"),
        ("AS_OF", None, "input", "Ultimo dia habil del mes a reportar — EDITAR esta celda", "input"),
        ("MES_ANT", "=EOMONTH(B3,-1)", "auto", "Ultimo dia del mes anterior", "calc"),
        ("YE_ANT", "=DATE(YEAR(B3)-1,12,31)", "auto", "31-dic del año anterior", "calc"),
        ("INI_12M", "=EDATE(B3,-12)", "auto", "12 meses antes de AS_OF", "calc"),
        ("ANALISTA", None, "input", "Nombre del analista que corre la plantilla", "input"),
        ("FECHA_CARGA", "=TODAY()", "auto", "Se rellena automaticamente al guardar", "calc"),
        ("BLOOMBERG_USUARIO", None, "input", "BBG UUID (opcional)", "input"),
        ("NOTAS_RAPIDAS", None, "input", "Cualquier anomalia detectada al cargar", "input"),
    ]

    headers = ["Parametro", "Valor", "Tipo", "Descripcion"]
    for j, h in enumerate(headers, start=1):
        c = ws.cell(row=2, column=j, value=h)
        style_header(c)

    for i, (name, formula, kind, desc, fill) in enumerate(fields, start=3):
        ws.cell(row=i, column=1, value=name).font = Font(bold=True)
        cell_val = ws.cell(row=i, column=2, value=formula)
        ws.cell(row=i, column=3, value=kind)
        ws.cell(row=i, column=4, value=desc)
        if fill == "input":
            cell_val.fill = INPUT_FILL
        elif fill == "calc":
            cell_val.fill = FORMULA_FILL
        if name in ("AS_OF", "MES_ANT", "YE_ANT", "INI_12M", "FECHA_CARGA"):
            cell_val.number_format = "yyyy-mm-dd"

    ws.cell(row=3, column=2, value=None)
    ws.cell(row=3, column=2).number_format = "yyyy-mm-dd"
    ws.cell(row=3, column=2).fill = INPUT_FILL

    ws.cell(row=2, column=2).comment = None
    # patch MES_REPORTE formula now that B3 reference is correct
    ws.cell(row=3, column=2, value=None)  # AS_OF input vacio
    # arreglar primera fila MES_REPORTE
    ws.cell(row=3, column=2, value=None)
    # set proper formula for MES_REPORTE (row 3 conflict resolved -- let's rebuild explicitly)

    auto_width(ws, max_width=70)
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["D"].width = 70


def sheet_parametros_v2(wb):
    """Version limpia. La de arriba quedo con un bug menor; uso esta."""
    name = "01_Parametros"
    if name in wb.sheetnames:
        del wb[name]
    ws = wb.create_sheet(name, 1)

    ws.cell(row=1, column=1, value="Parametros del corte").font = Font(bold=True, size=14, color="1F3A5F")

    headers = ["Parametro", "Valor", "Tipo", "Descripcion"]
    for j, h in enumerate(headers, start=1):
        c = ws.cell(row=2, column=j, value=h)
        style_header(c)

    # filas: (name, value_or_formula, kind, desc, is_input, number_format)
    rows = [
        ("AS_OF",            None,                              "input", "Ultimo dia habil del mes a reportar — EDITAR esta celda", True,  "yyyy-mm-dd"),
        ("MES_REPORTE",      '=TEXT(B3,"yyyy-mm")',             "auto",  "YYYY-MM del corte",                                       False, None),
        ("MES_ANT",          "=EOMONTH(B3,-1)",                 "auto",  "Ultimo dia del mes anterior",                             False, "yyyy-mm-dd"),
        ("YE_ANT",           "=DATE(YEAR(B3)-1,12,31)",         "auto",  "31-dic del año anterior",                                 False, "yyyy-mm-dd"),
        ("INI_12M",          "=EDATE(B3,-12)",                  "auto",  "12 meses antes de AS_OF",                                 False, "yyyy-mm-dd"),
        ("ANALISTA",         None,                              "input", "Nombre del analista que corre la plantilla",              True,  None),
        ("FECHA_CARGA",      "=TODAY()",                        "auto",  "Fecha en que se guardo este archivo",                     False, "yyyy-mm-dd"),
        ("BBG_UUID",         None,                              "input", "BBG UUID (opcional)",                                     True,  None),
        ("NOTAS_RAPIDAS",    None,                              "input", "Cualquier anomalia detectada al cargar",                  True,  None),
    ]
    for i, (n, v, k, d, is_input, fmt) in enumerate(rows, start=3):
        ws.cell(row=i, column=1, value=n).font = Font(bold=True)
        cell = ws.cell(row=i, column=2, value=v)
        ws.cell(row=i, column=3, value=k)
        ws.cell(row=i, column=4, value=d)
        if is_input:
            cell.fill = INPUT_FILL
        else:
            cell.fill = FORMULA_FILL
        if fmt:
            cell.number_format = fmt

    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["C"].width = 12
    ws.column_dimensions["D"].width = 72


# --------------------------------------------------------------------------- #
# Hoja: 02_Datos — todos los spots en formato long
# --------------------------------------------------------------------------- #
def sheet_datos(wb):
    ws = wb.create_sheet("02_Datos")
    headers = [
        "#", "categoria", "region", "instrument", "tenor_label", "tenor_years",
        "ticker", "field", "unit",
        "val_AS_OF", "val_MES_ANT", "val_YE_ANT", "val_INI_12M",
        "nota",
    ]
    for j, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=j, value=h)
        style_header(c)
    ws.row_dimensions[1].height = 22

    # Las fechas vienen de 01_Parametros!$B$3 (AS_OF), $B$5 (MES_ANT), $B$6 (YE_ANT), $B$7 (INI_12M)
    # Despues de la reordenacion de rows en sheet_parametros_v2:
    #   B3 = AS_OF
    #   B4 = MES_REPORTE (texto)
    #   B5 = MES_ANT
    #   B6 = YE_ANT
    #   B7 = INI_12M
    REF_AS_OF = "'01_Parametros'!$B$3"
    REF_MES_ANT = "'01_Parametros'!$B$5"
    REF_YE_ANT = "'01_Parametros'!$B$6"
    REF_INI_12M = "'01_Parametros'!$B$7"

    def bdh_point(ticker_cell, field_cell, date_ref):
        # Formula que devuelve solo el valor (sin la fecha) para un dia especifico.
        # Para Excel 365 con dynamic arrays, BDH(...) devuelve un array {fecha, valor};
        # con INDEX(...,1,2) tomamos solo el segundo elemento (el valor).
        # Si por alguna razon BDH devuelve un escalar, INDEX simplemente devuelve el valor.
        return (
            f'=IFERROR(INDEX(BDH({ticker_cell},{field_cell},'
            f'{date_ref},{date_ref},"Days=A","Fill=B","Dir=H"),1,2),'
            f'BDH({ticker_cell},{field_cell},{date_ref},{date_ref},"Days=A","Fill=B"))'
        )

    for i, (cat, region, instr, tenor_label, tenor_years, ticker, field, unit, nota) in enumerate(INSTRUMENTOS, start=2):
        ws.cell(row=i, column=1, value=i - 1)
        ws.cell(row=i, column=2, value=cat)
        ws.cell(row=i, column=3, value=region)
        ws.cell(row=i, column=4, value=instr)
        ws.cell(row=i, column=5, value=tenor_label)
        ws.cell(row=i, column=6, value=tenor_years)
        c_ticker = ws.cell(row=i, column=7, value=ticker)
        c_field = ws.cell(row=i, column=8, value=field)
        ws.cell(row=i, column=9, value=unit)

        # Referencias absolutas a la celda del ticker y field para cada fila
        ticker_ref = f"$G${i}"
        field_ref = f"$H${i}"

        ws.cell(row=i, column=10, value=bdh_point(ticker_ref, field_ref, REF_AS_OF)).fill = FORMULA_FILL
        ws.cell(row=i, column=11, value=bdh_point(ticker_ref, field_ref, REF_MES_ANT)).fill = FORMULA_FILL
        ws.cell(row=i, column=12, value=bdh_point(ticker_ref, field_ref, REF_YE_ANT)).fill = FORMULA_FILL
        ws.cell(row=i, column=13, value=bdh_point(ticker_ref, field_ref, REF_INI_12M)).fill = FORMULA_FILL

        ws.cell(row=i, column=14, value=nota)

    # column widths
    widths = [4, 14, 8, 26, 12, 6, 22, 22, 8, 12, 12, 12, 12, 50]
    for j, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(j)].width = w

    ws.freeze_panes = "B2"


# --------------------------------------------------------------------------- #
# Hoja: 03_SOFR_Futures
# --------------------------------------------------------------------------- #
def sheet_sofr_futures(wb):
    ws = wb.create_sheet("03_SOFR_Futures")
    headers = ["#", "contract_code", "description", "AS_OF_price", "AS_OF_implied_rate", "MES_ANT_price", "MES_ANT_implied_rate", "open_interest"]
    for j, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=j, value=h)
        style_header(c)

    REF_AS_OF = "'01_Parametros'!$B$3"
    REF_MES_ANT = "'01_Parametros'!$B$5"

    for i, (code, desc) in enumerate(SOFR_FUTURES, start=2):
        ws.cell(row=i, column=1, value=i - 1)
        ws.cell(row=i, column=2, value=code)
        ws.cell(row=i, column=3, value=desc)
        # Price
        price_asof = f'=IFERROR(INDEX(BDH($B${i},"PX_LAST",{REF_AS_OF},{REF_AS_OF},"Days=A","Fill=B"),1,2),BDH($B${i},"PX_LAST",{REF_AS_OF},{REF_AS_OF},"Days=A","Fill=B"))'
        price_prev = f'=IFERROR(INDEX(BDH($B${i},"PX_LAST",{REF_MES_ANT},{REF_MES_ANT},"Days=A","Fill=B"),1,2),BDH($B${i},"PX_LAST",{REF_MES_ANT},{REF_MES_ANT},"Days=A","Fill=B"))'
        ws.cell(row=i, column=4, value=price_asof).fill = FORMULA_FILL
        ws.cell(row=i, column=5, value=f"=100-D{i}").fill = FORMULA_FILL
        ws.cell(row=i, column=6, value=price_prev).fill = FORMULA_FILL
        ws.cell(row=i, column=7, value=f"=100-F{i}").fill = FORMULA_FILL
        # Open interest
        oi = f'=IFERROR(INDEX(BDH($B${i},"OPEN_INT",{REF_AS_OF},{REF_AS_OF},"Days=A","Fill=B"),1,2),BDH($B${i},"OPEN_INT",{REF_AS_OF},{REF_AS_OF},"Days=A","Fill=B"))'
        ws.cell(row=i, column=8, value=oi).fill = FORMULA_FILL

    widths = [4, 18, 30, 14, 18, 14, 18, 16]
    for j, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(j)].width = w

    # Nota debajo
    nota_row = len(SOFR_FUTURES) + 4
    ws.cell(row=nota_row, column=1, value="Nota").font = Font(bold=True)
    ws.cell(row=nota_row, column=2, value="SFRn Comdty = continuous front-month rolling future n (n=1 es el primer vencimiento activo).")
    ws.cell(row=nota_row + 1, column=2, value="Implied rate = 100 - price (convencion CME).")
    ws.cell(row=nota_row + 2, column=2, value="Si el ticker continuous no esta disponible, sustituir por el codigo del contrato especifico (ej. SFRZ6 Comdty para dic-2026).")


# --------------------------------------------------------------------------- #
# Hoja: 04_FedWatch (paste manual)
# --------------------------------------------------------------------------- #
def sheet_fedwatch(wb):
    ws = wb.create_sheet("04_FedWatch")
    ws.cell(row=1, column=1, value="FedWatch — paste manual desde pantalla WIRP de Bloomberg").font = Font(bold=True, size=12, color="1F3A5F")
    ws.cell(row=2, column=1, value="Pegar como valores. Esta hoja NO tiene formulas BDP.").font = Font(italic=True, color="666666")

    headers = ["meeting_date", "current_rate_implied", "prob_-50bps", "prob_-25bps", "prob_0bps", "prob_+25bps", "prob_+50bps", "notas"]
    for j, h in enumerate(headers, start=1):
        c = ws.cell(row=4, column=j, value=h)
        style_header(c)

    # Filas placeholders para 6 reuniones FOMC proximas
    for i in range(5, 11):
        ws.cell(row=i, column=1, value=None).number_format = "yyyy-mm-dd"
        for j in range(2, 8):
            ws.cell(row=i, column=j, value=None).fill = INPUT_FILL

    widths = [16, 22, 14, 14, 14, 14, 14, 40]
    for j, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(j)].width = w


# --------------------------------------------------------------------------- #
# Hoja: 05_Notas_Analista
# --------------------------------------------------------------------------- #
def sheet_notas(wb):
    ws = wb.create_sheet("05_Notas_Analista")
    ws.cell(row=1, column=1, value="Notas del analista").font = Font(bold=True, size=14, color="1F3A5F")
    ws.cell(row=3, column=1, value="Cualquier observacion: tickers que fallaron, eventos del mes, anomalias, sugerencias.").font = Font(italic=True)
    ws.cell(row=5, column=1, value="Tickers fallidos / corregidos").font = Font(bold=True)
    for i in range(6, 16):
        ws.cell(row=i, column=1, value="—")
        ws.cell(row=i, column=2, value="").fill = INPUT_FILL
    ws.cell(row=17, column=1, value="Eventos relevantes del mes").font = Font(bold=True)
    for i in range(18, 28):
        ws.cell(row=i, column=2, value="").fill = INPUT_FILL
    ws.cell(row=29, column=1, value="Sugerencias para el corte siguiente").font = Font(bold=True)
    for i in range(30, 40):
        ws.cell(row=i, column=2, value="").fill = INPUT_FILL
    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 90


# --------------------------------------------------------------------------- #
# Hoja: 99_Envio (instrucciones de devolucion)
# --------------------------------------------------------------------------- #
def sheet_envio(wb):
    ws = wb.create_sheet("99_Envio")
    rows = [
        ("Como devolver este archivo", "header"),
        ("", "blank"),
        ("OPCION 1 — Recomendada — Upload directo a GitHub (web)", "h2"),
        ("1. Guardar el archivo con nombre: BloombergTemplate_TasasMercantil_<YYYY-MM>.xlsx", "body"),
        ("2. En el navegador (incluido movil) ir a: github.com/andresborrerom/credito_Panama", "body"),
        ("3. Cambiar al branch: claude/tasas-mercantil-report-Q8sFt", "body"),
        ("4. Navegar a la carpeta: ProyectoTasasMercantil/cortes/<YYYY-MM>/input/", "body"),
        ("   (si no existe, crearla con 'Add file -> Create new file' y nombre 'input/.gitkeep')", "body"),
        ("5. 'Add file' -> 'Upload files' -> arrastrar el xlsx", "body"),
        ("6. Commit message sugerido: 'ingest(corte YYYY-MM): input Bloomberg cargado por <analista>'", "body"),
        ("7. Click 'Commit changes'.", "body"),
        ("", "blank"),
        ("OPCION 2 — Correo electronico", "h2"),
        ("Enviar el .xlsx por correo al equipo (Andres + Camilo + Claude session si aplica).", "body"),
        ("Asunto sugerido: 'Tasas Mercantil — Input Bloomberg <YYYY-MM>'", "body"),
        ("Quien recibe se encarga del upload a GitHub.", "body"),
        ("", "blank"),
        ("OPCION 3 — OneDrive compartido (si la organizacion lo prefiere)", "h2"),
        ("Subir a OneDrive en una carpeta acordada. La sincronizacion local hace el resto si esta configurada.", "body"),
        ("No es la via mas directa pero funciona si el flujo organizacional lo requiere.", "body"),
        ("", "blank"),
        ("Verificacion despues de subir", "h2"),
        ("Una vez cargado, el equipo abre una sesion y corre el pipeline de validacion.", "body"),
        ("Si el archivo paso validacion, llega confirmacion. Si fallo, llega lista de campos a revisar.", "body"),
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
# Main
# --------------------------------------------------------------------------- #
def main():
    wb = Workbook()
    # remover hoja default
    default = wb.active
    wb.remove(default)

    sheet_instrucciones(wb)
    sheet_parametros_v2(wb)
    sheet_datos(wb)
    sheet_sofr_futures(wb)
    sheet_fedwatch(wb)
    sheet_notas(wb)
    sheet_envio(wb)

    out = "/home/user/credito_Panama/ProyectoTasasMercantil/plantilla_bloomberg/BloombergTemplate_TasasMercantil.xlsx"
    wb.save(out)
    print(f"Generado: {out}")
    print(f"Hojas: {wb.sheetnames}")
    print(f"Total instrumentos: {len(INSTRUMENTOS)}")
    print(f"Total SOFR futures: {len(SOFR_FUTURES)}")


if __name__ == "__main__":
    main()
