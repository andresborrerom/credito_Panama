"""Catálogo de endpoints JSON descubiertos en latinexbolsa.com.

Todos devuelven { "order": [...], "filters": [...], "data": [...] } salvo nota.
Reverse-engineered desde el bundle JS público (sin auth, sin rate-limit detectado).
"""

BASE = "https://www.latinexbolsa.com"

EMISIONES_ACTIVAS = f"{BASE}/emisor/emisiones/activas/all"
TRANSACCIONES = f"{BASE}/emisor/transacciones/mercado"  # ?rango=1D|1M|3M|6M|1Y|5Y|10Y
INSTRUMENTO_HISTORICO = f"{BASE}/emisor/detalle/instrumento/historico"  # ?instrumento=NEMO&rango=1Y
INSTRUMENTO_RESUMEN = f"{BASE}/emisor/detalle/instrumento/resumen"  # ?instrumento=NEMO
INSTRUMENTO_PAGO = f"{BASE}/emisor/detalle/instrumento/pago"  # ?instrumento=NEMO&rango=1D
EMISOR_DETALLE = f"{BASE}/emisor/detalle/emisor"  # ?code=CODE
EMISOR_CIFRAS = f"{BASE}/emisor/detalle/emisor/cifras"  # ?code=CODE
EMISOR_INSTRUMENTOS = f"{BASE}/emisor/detalle/emisor/instrumento"  # ?code=CODE
VOLUMEN_EMISOR = f"{BASE}/volumen/emisor"
OFERTAS_HOME = f"{BASE}/ofertas/mercado/home"
EMISIONES_SOSTENIBLES = f"{BASE}/emisor/emisiones/sostenibles"
EMISIONES_NUEVAS = f"{BASE}/emisor/nuevas/list"  # ?rango=1D
EMISIONES_TRAMITES = f"{BASE}/emisor/emisiones/tramites"
EMISIONES_PROSPECTOS = f"{BASE}/emisor/emisiones/nuevos/prospectos"
RANKING_CREADORES = f"{BASE}/ranking/creadores"
HECHOS_RELEVANTES = f"{BASE}/emisor/hechos/relevantes"

# Endpoint externo público (sin key) para benchmark UST
US_TREASURY_YIELDS = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
)

UA = "Mozilla/5.0 (compatible; PanamaFixedIncomeStudy/0.1; +https://github.com/andresborrerom/credito_panama)"
