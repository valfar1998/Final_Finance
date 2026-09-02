"""Asset registry with region/country metadata."""

DEFAULT_ASSETS = [
    # --- USA ---
    {"id": "aapl", "name": "Apple", "type": "azione", "stooq": "aapl.us", "yf": "AAPL", "region": "usa", "country": "USA"},
    {"id": "msft", "name": "Microsoft", "type": "azione", "stooq": "msft.us", "yf": "MSFT", "region": "usa", "country": "USA"},
    {"id": "nvda", "name": "NVIDIA", "type": "azione", "stooq": "nvda.us", "yf": "NVDA", "region": "usa", "country": "USA"},
    {"id": "tsla", "name": "Tesla", "type": "azione", "stooq": "tsla.us", "yf": "TSLA", "region": "usa", "country": "USA"},
    {"id": "pltr", "name": "Palantir", "type": "azione", "stooq": "pltr.us", "yf": "PLTR", "region": "usa", "country": "USA", "startup": True},
    {"id": "sofi", "name": "SoFi", "type": "azione", "stooq": "sofi.us", "yf": "SOFI", "region": "usa", "country": "USA", "startup": True},
    {"id": "snap", "name": "Snap", "type": "azione", "stooq": "snap.us", "yf": "SNAP", "region": "usa", "country": "USA", "startup": True},
    {"id": "rivn", "name": "Rivian", "type": "azione", "stooq": "rivn.us", "yf": "RIVN", "region": "usa", "country": "USA", "startup": True},
    {"id": "bnd", "name": "Vanguard Total Bond (BND)", "type": "etf", "stooq": "bnd.us", "yf": "BND", "region": "usa", "country": "USA"},
    {"id": "agg", "name": "iShares Core US Aggregate Bond (AGG)", "type": "etf", "stooq": "agg.us", "yf": "AGG", "region": "usa", "country": "USA"},
    # --- Italia ---
    {"id": "enel", "name": "Enel", "type": "azione", "stooq": "enel.it", "yf": "ENEL.MI", "region": "italia", "country": "Italia"},
    {"id": "eni", "name": "Eni", "type": "azione", "stooq": "eni.it", "yf": "ENI.MI", "region": "italia", "country": "Italia"},
    {"id": "isp", "name": "Intesa Sanpaolo", "type": "azione", "stooq": "isp.it", "yf": "ISP.MI", "region": "italia", "country": "Italia"},
    {"id": "stm", "name": "STMicroelectronics", "type": "azione", "stooq": "stm.it", "yf": "STMMI.MI", "region": "italia", "country": "Italia", "startup": True},
    {"id": "rec", "name": "Recordati", "type": "azione", "stooq": "rec.it", "yf": "REC.MI", "region": "italia", "country": "Italia", "startup": True},
    # --- Europa (ETF + azioni) ---
    {"id": "vwce", "name": "Vanguard FTSE All-World (VWCE)", "type": "etf", "stooq": "vwce.de", "yf": "VWCE.DE", "region": "europa", "country": "Germania"},
    {"id": "swda", "name": "iShares MSCI World (SWDA)", "type": "etf", "stooq": "swda.uk", "yf": "SWDA.L", "region": "uk", "country": "Regno Unito"},
    {"id": "cspx", "name": "iShares S&P 500 (CSPX)", "type": "etf", "stooq": "cspx.uk", "yf": "CSPX.L", "region": "uk", "country": "Regno Unito"},
    {"id": "sap", "name": "SAP", "type": "azione", "stooq": "sap.de", "yf": "SAP.DE", "region": "europa", "country": "Germania"},
    {"id": "asml", "name": "ASML", "type": "azione", "stooq": "asml.us", "yf": "ASML", "region": "europa", "country": "Paesi Bassi"},
]

REGIONS = [
    {"id": "all", "label": "Tutte le regioni"},
    {"id": "usa", "label": "USA"},
    {"id": "italia", "label": "Italia"},
    {"id": "europa", "label": "Europa"},
    {"id": "uk", "label": "Regno Unito"},
    {"id": "asia", "label": "Asia"},
    {"id": "canada", "label": "Canada"},
]

# Soglie sezione startup (azioni a basso prezzo + consigliate analisti)
STARTUP_MAX_PRICE_USD = 80.0
STARTUP_MIN_BUYABILITY = 55.0
STARTUP_MIN_UPSIDE_PCT = 10.0
