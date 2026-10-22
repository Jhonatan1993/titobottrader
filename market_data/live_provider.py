"""
Proveedor de datos de mercado en vivo para IQ Option Forex CFD.
Obtiene tasas interbancarias reales de Forex vía HTTP para alimentar el feed.
Solo Forex CFD — sin Binance ni Alpaca.
"""
import urllib.request
import json
import ssl
import time
from typing import Dict, Optional


class LiveForexRatesProvider:
    """
    Obtiene tasas de cambio Forex interbancarias reales.
    Fuentes: open.er-api.com y frankfurter.dev como fallback.
    Devuelve pares Forex directamente operables en IQ Option CFD.
    """

    # Pares Forex CFD permitidos en IQ Option
    FOREX_PAIRS = [
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
        "USDCAD", "USDCHF", "NZDUSD", "EURGBP",
        "EURJPY", "GBPJPY"
    ]

    def __init__(self):
        self._cache: Dict[str, float] = {}
        self._last_fetch: float = 0.0
        self._ttl: float = 4.0  # refrescar cada 4 segundos

    def get_rates(self) -> Dict[str, float]:
        """Retorna las tasas Forex actualizadas; usa caché si TTL no expiró."""
        now = time.time()
        if now - self._last_fetch < self._ttl and self._cache:
            return dict(self._cache)
        try:
            ctx = ssl._create_unverified_context()
            rates: Dict[str, float] = {}

            # Intento 1: open.er-api.com
            try:
                req = urllib.request.Request(
                    "https://open.er-api.com/v6/latest/USD",
                    headers={"User-Agent": "TitoBotTrader/3.0"}
                )
                with urllib.request.urlopen(req, timeout=3.0, context=ctx) as resp:
                    data = json.loads(resp.read().decode())
                    if data.get("result") == "success":
                        rates = data.get("rates", {})
            except Exception:
                pass

            # Intento 2: frankfurter.dev
            if not rates:
                try:
                    req2 = urllib.request.Request(
                        "https://api.frankfurter.dev/v1/latest?from=USD",
                        headers={"User-Agent": "TitoBotTrader/3.0"}
                    )
                    with urllib.request.urlopen(req2, timeout=3.0, context=ctx) as resp2:
                        rates = json.loads(resp2.read().decode()).get("rates", {})
                except Exception:
                    pass

            if rates:
                self._update_cache(rates)
                self._last_fetch = now
        except Exception:
            pass
        return dict(self._cache)

    def _update_cache(self, rates: Dict[str, float]) -> None:
        if "EUR" in rates and float(rates["EUR"]) > 0:
            self._cache["EURUSD"] = round(1.0 / float(rates["EUR"]), 5)
        if "GBP" in rates and float(rates["GBP"]) > 0:
            self._cache["GBPUSD"] = round(1.0 / float(rates["GBP"]), 5)
        if "JPY" in rates and float(rates["JPY"]) > 0:
            self._cache["USDJPY"] = round(float(rates["JPY"]), 3)
        if "CAD" in rates and float(rates["CAD"]) > 0:
            self._cache["USDCAD"] = round(float(rates["CAD"]), 5)
        if "CHF" in rates and float(rates["CHF"]) > 0:
            self._cache["USDCHF"] = round(float(rates["CHF"]), 5)
        if "AUD" in rates and float(rates["AUD"]) > 0:
            self._cache["AUDUSD"] = round(1.0 / float(rates["AUD"]), 5)
        if "NZD" in rates and float(rates["NZD"]) > 0:
            self._cache["NZDUSD"] = round(1.0 / float(rates["NZD"]), 5)
        if "EUR" in rates and "GBP" in rates and float(rates["EUR"]) > 0 and float(rates["GBP"]) > 0:
            self._cache["EURGBP"] = round(float(rates["GBP"]) / float(rates["EUR"]), 5)
        if "EUR" in rates and "JPY" in rates and float(rates["EUR"]) > 0:
            self._cache["EURJPY"] = round(float(rates["JPY"]) / float(rates["EUR"]), 3)
        if "GBP" in rates and "JPY" in rates and float(rates["GBP"]) > 0:
            self._cache["GBPJPY"] = round(float(rates["JPY"]) / float(rates["GBP"]), 3)

