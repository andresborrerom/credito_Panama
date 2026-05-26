"""Mapeo de calificación crediticia por emisor — PROXY V0 + actualizaciones puntuales.

Hay DOS dimensiones de calificación:

  (a) ISSUER_RATING_PROXY  — rating "histórico" que se aplica a todos los trades
                              de un emisor, indistintamente de la fecha del trade.
                              Se usa para los análisis del estudio retrospectivo
                              (sector bancario, percentiles 5y, etc.) y NO se
                              re-escribe cuando un emisor sube/baja de rating,
                              porque eso distorsionaría el contexto de cada trade.

  (b) CURRENT_RATINGS      — rating ACTUAL (snapshot a la fecha indicada).
                              Se usa para análisis prospectivos (pricing de
                              emisiones nuevas, recomendación a Mercantil, etc.)
                              donde lo relevante es la calidad crediticia HOY,
                              no la promedio histórica.

ADVERTENCIA: ambos son proxy curado. Se reemplazarán por calificaciones
oficiales cuando se incorpore el dump de Bloomberg.

Escala usada: nacional Panamá (sufijo (pan)):
  T1: AAA(pan)         — soberano local y bancos sistémicos top
  T2: AA(pan)/A+(pan)  — bancos grandes establecidos, utilities reguladas
  T3: A(pan)           — bancos medianos, corporates establecidos
  T4: BBB(pan)         — fideicomisos hipotecarios, real estate con track record
  T5: BB(pan)/Unrated  — VCN pequeños, corporativos sin rating público claro

La asignación 'tier' se usa para análisis. Los emisores no listados aquí
caen al proxy basado en sector (curves.CREDIT_TIERS).
"""

# ----------------------------- HISTÓRICO ---------------------------------- #
# Top emisores por volumen de trades (top 50 cubren ~85% del mercado)
# Refleja el rating PROMEDIO de los últimos 5-10 años. NO se actualiza por
# upgrades/downgrades recientes — eso pertenece a CURRENT_RATINGS.
ISSUER_RATING_PROXY = {
    # T1 — soberano y top bancos sistémicos
    "REPÚBLICA DE PANAMÁ":                              ("T1", "AAA(pan)"),
    "REPUBLICA DE PANAMA":                              ("T1", "AAA(pan)"),
    "BANCO GENERAL, S.A.":                              ("T1", "AAA(pan)"),
    "GRUPO FINANCIERO BG, S.A.":                        ("T1", "AAA(pan)"),
    "EMPRESA GENERAL DE INVERSIONES, S.A.":             ("T1", "AAA(pan)"),

    # T2 — bancos grandes y utilities
    "BANISTMO, S.A.":                                   ("T2", "AA(pan)"),
    "GLOBAL BANK CORPORATION":                          ("T2", "AA(pan)"),
    "BAC INTERNATIONAL BANK, INC.":                     ("T2", "AA(pan)"),
    "MERCANTIL BANCO, S.A.":                            ("T2", "AA(pan)"),
    "MULTIBANK INC.":                                   ("T2", "AA(pan)"),
    "BANCO ALIADO, S.A.":                               ("T2", "AA(pan)"),
    "BANCO LAFISE PANAMA, S.A.":                        ("T2", "AA(pan)"),
    "MERCANTIL HOLDING FINANCIERO INTERNACIONAL, S.A.": ("T2", "AA(pan)"),
    "MERCANTIL SERVICIOS FINANCIEROS INTERNACIONAL, S.A.": ("T2", "AA(pan)"),
    "ENA NORTE TRUST":                                  ("T2", "AA(pan)"),  # autopista cobro peaje
    "ENA SUR, S.A.":                                    ("T2", "AA(pan)"),
    "ELEKTRA NORESTE, S.A.":                            ("T2", "AA(pan)"),
    "AES PANAMA, S.R.L.":                               ("T2", "AA(pan)"),
    "ETESA":                                            ("T2", "AA(pan)"),

    # T3 — bancos medianos, corporativos establecidos
    "BANCO INTERNACIONAL DE COSTA RICA, S.A.":          ("T3", "A(pan)"),
    "BANCO PANAMA, S.A.":                               ("T3", "A(pan)"),
    "PRIVAL BANK, S.A.":                                ("T3", "A(pan)"),
    "CREDICORP BANK, S.A.":                             ("T3", "A(pan)"),
    "METROBANK, S.A.":                                  ("T3", "A(pan)"),
    "TOWERBANK INTERNATIONAL, INC.":                    ("T3", "A(pan)"),
    "ST. GEORGES BANK & COMPANY INC.":                  ("T3", "A(pan)"),
    "BANCO PICHINCHA PANAMA, S.A.":                     ("T3", "A(pan)"),
    "BANISI, S.A.":                                     ("T3", "A(pan)"),
    "BANESCO (PANAMÁ), S.A.":                           ("T3", "A(pan)"),  # histórico A(pan) hasta 11-may-2026
    "PETROLEOS DELTA, S.A.":                            ("T3", "A(pan)"),
    "COCHEZ Y COMPAÑIA, S.A.":                          ("T3", "A(pan)"),
    "GRUPO ASSA, S.A.":                                 ("T3", "A(pan)"),

    # T4 — fideicomisos hipotecarios, financieras especializadas
    "BANCO LA HIPOTECARIA, S.A.":                       ("T4", "BBB(pan)"),
    "HIPOTECARIA METROCREDIT, S.A.":                    ("T4", "BBB(pan)"),
    "PRIMER FIDEICOMISO DE BONOS DE PRESTAMOS PERSONALES CCB": ("T4", "BBB(pan)"),
    "CORPORACION DE FINANZAS DEL PAIS,S.A. (PANACREDIT)": ("T4", "BBB(pan)"),
    "FONDO GENERAL DE INVERSIONES, S.A.":               ("T4", "BBB(pan)"),
    "ARROW CAPITAL CORP.":                              ("T4", "BBB(pan)"),
    "FINANCIA CREDIT, S.A.":                            ("T4", "BBB(pan)"),
    "UNION NACIONAL DE EMPRESAS, S.A.":                 ("T4", "BBB(pan)"),
    "CORPORACION INTERAMERICANA PARA EL FINANCIAMIENTO DE INFRAESTRUCTRURA, S.A. (CIFI)": ("T4", "BBB(pan)"),
    "PANAMA POWER HOLDINGS, INC":                       ("T4", "BBB(pan)"),
    "HYDRO CAISAN, S.A.":                               ("T4", "BBB(pan)"),

    # T5 — small, real estate developers, VCN pequeños, unrated
    "SOCIEDAD URBANIZADORA DEL CARIBE, S.A.":           ("T5", "BB(pan)/NR"),
    "LOS CASTILLOS REAL ESTATE, INC.":                  ("T5", "BB(pan)/NR"),
    "INMOBILIARIA PANAMA CAR RENTAL, S.A.":             ("T5", "BB(pan)/NR"),
    "CM REALTY, S.A.":                                  ("T5", "BB(pan)/NR"),
    "MAREVALLEY CORPORATION":                           ("T5", "BB(pan)/NR"),
    "DESARROLLOS COMERCIALES, S.A.":                    ("T5", "BB(pan)/NR"),
    "PARQUE INDUSTRIAL Y CORPORATIVO SUR, S.A.":        ("T5", "BB(pan)/NR"),
    "INVERSIONES LEINA, S.A.":                          ("T5", "BB(pan)/NR"),
    "LATIN AMERICAN KRAFT INVESTMENTS, INC. Y SUBSIDIARIAS": ("T5", "BB(pan)/NR"),
}

# Fallback por sector (cuando emisor no está en mapeo manual)
SECTOR_FALLBACK_TIER = {
    "Gobierno":       ("T1", "AAA(pan) [sector-proxy]"),
    "Financiero":     ("T3", "A(pan) [sector-proxy]"),
    "Utilidades":     ("T2", "AA(pan) [sector-proxy]"),
    "Energía":        ("T3", "A(pan) [sector-proxy]"),
    "Comunicaciones": ("T3", "A(pan) [sector-proxy]"),
    "Industriales":   ("T4", "BBB(pan) [sector-proxy]"),
    "Consumo Básico": ("T4", "BBB(pan) [sector-proxy]"),
    "Consumo Discresional": ("T4", "BBB(pan) [sector-proxy]"),
    "Bienes Raíces":  ("T5", "BB(pan)/NR [sector-proxy]"),
    "Materiales":     ("T4", "BBB(pan) [sector-proxy]"),
    "Salud":          ("T4", "BBB(pan) [sector-proxy]"),
    "Tecnología":     ("T4", "BBB(pan) [sector-proxy]"),
    "Servicios":      ("T4", "BBB(pan) [sector-proxy]"),
}

# Bonos del Tesoro siempre T1 sin importar sector
GOVT_INSTRUMENTS = {"BONOS DEL TESORO", "NOTAS DEL TESORO", "LETRAS DEL TESORO"}


def assign_rating(emisor: str | None, sector: str | None, instrumento: str | None) -> tuple[str, str]:
    """Devuelve (tier, rating_proxy_label) para un trade/instrumento.
    Esta es la asignación HISTÓRICA, usada para etiquetar trades en la base
    indistintamente de la fecha. Para rating ACTUAL ver CURRENT_RATINGS.
    """
    if instrumento in GOVT_INSTRUMENTS:
        return ("T1", "AAA(pan)")
    if emisor and isinstance(emisor, str):
        em_clean = emisor.strip().upper()
        for key, val in ISSUER_RATING_PROXY.items():
            if em_clean == key.upper():
                return val
    if sector and isinstance(sector, str):
        return SECTOR_FALLBACK_TIER.get(sector, ("T5", "Unrated [no-sector]"))
    return ("T5", "Unrated")


TIER_ORDER = ["T1", "T2", "T3", "T4", "T5"]
TIER_DESC = {
    "T1": "AAA(pan) — soberano + bancos sistémicos top",
    "T2": "AA(pan)/A+(pan) — bancos grandes, utilities",
    "T3": "A(pan)   — bancos medianos, corporativos establecidos",
    "T4": "BBB(pan) — hipotecarios, financieras",
    "T5": "BB(pan)/NR — small caps, real estate, VCN pequeños, unrated",
}


# ----------------------------- ACTUAL ------------------------------------- #
# Snapshot del rating ACTUAL (a la fecha indicada).
# Cada entrada: emisor -> {
#   "tier": "T1..T5",
#   "rating": "AA(pan)" etc.,
#   "agency": "Fitch CA" | "Equilibrium" | "PCR" | "Moody's Local",
#   "outlook": "Estable" | "Positiva" | "Negativa" | "Observación",
#   "as_of": "YYYY-MM-DD",
#   "source_url": "https://...",
#   "note": "comentario libre, ej. razón del último upgrade"
# }
CURRENT_RATINGS = {
    "BANESCO (PANAMÁ), S.A.": {
        "tier": "T2",
        "rating": "A+(pan)",
        "agency": "Fitch Ratings",
        "outlook": "Estable",
        "as_of": "2026-05-11",
        "source_url": "https://www.fitchratings.com",
        "note": (
            "Upgrade de A(pan) a A+(pan). Razones: ingresos operativos crecientes, "
            "utilidad operativa/APR > 1.3%, CET1 ~12% incluyendo provisiones dinámicas y AT1."
        ),
    },
    "MERCANTIL BANCO, S.A.": {
        "tier": "T3",
        "rating": "A(pa)",
        "agency": "Moody's Local Panamá",
        "outlook": "Estable",
        "as_of": "2025-05-29",
        "source_url": "https://moodyslocal.com.pa/sectores/entidades-financieras/bancos/mercantil-banco-s-a-y-sus-filiales/",
        "note": (
            "Moody's Local PA califica MBSA en A(pa) Estable (entidad y bonos corporativos) "
            "y ML A-1(pa) para VCN. Fitch tenía BBB+(pan) Estable pero RETIRÓ cobertura "
            "el 20-may-2025 por razones comerciales (commercial reasons), por lo que solo "
            "Moody's Local es calificación viva. Reportes citan presión por morosidad "
            "heredada de Capital Bank tras la fusión. Mercantil queda UN NOTCH POR DEBAJO "
            "de Banesco (A+(pan) Fitch desde may-2026)."
        ),
    },
    "MERCANTIL HOLDING FINANCIERO INTERNACIONAL, S.A.": {
        "tier": "T3",
        "rating": "A-(pa) [estimado]",
        "agency": "Moody's Local Panamá (inferido)",
        "outlook": "Estable",
        "as_of": "2025-12-31",
        "source_url": "https://supervalores.gob.pa/files/registros/emisiones/Mercantil-Holding-Financiero-Internacional/Prospecto-Informativo-Mercantil-Holding.pdf",
        "note": (
            "Holding intermedio entre MSFI y Mercantil Banco. Calificación típicamente "
            "uno o dos notches por debajo del Banco regulado. Estimado A-(pa) — pendiente "
            "confirmación oficial con la calificadora."
        ),
    },
}


def current_rating(emisor: str) -> dict | None:
    """Devuelve el rating ACTUAL si está disponible; None si solo hay proxy histórico."""
    if not emisor:
        return None
    em_clean = emisor.strip().upper()
    for key, val in CURRENT_RATINGS.items():
        if em_clean == key.upper():
            return val
    return None

