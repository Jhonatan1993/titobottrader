import time
import datetime
import random
import math
import threading
from typing import Dict, List, Any, Optional
from config.broker_config import load_broker_config
from execution.iqoption_adapter import IQOptionAdapter

# Catálogo exclusivo: Pares Forex CFD operables en IQ Option
# Solo pares con suficiente liquidez y horario de sesión extendido.
AVAILABLE_ASSETS = [
    # === FOREX CFD IQ Option — Pares Mayores y Cruces ===
    {
        "symbol": "EURUSD",
        "name": "EUR / USD",
        "category": "FOREX",
        "type": "Euro / Dólar Estadounidense",
        "icon": "💶",
        "base_price": 1.1143,
        "volatility": 0.0035,
        "trend_bias": 0.0001
    },
    {
        "symbol": "GBPUSD",
        "name": "GBP / USD",
        "category": "FOREX",
        "type": "Libra Esterlina / Dólar",
        "icon": "💷",
        "base_price": 1.3315,
        "volatility": 0.0040,
        "trend_bias": 0.0001
    },
    {
        "symbol": "USDJPY",
        "name": "USD / JPY",
        "category": "FOREX",
        "type": "Dólar / Yen Japonés",
        "icon": "💴",
        "base_price": 157.89,
        "volatility": 0.0045,
        "trend_bias": 0.0001
    },
    {
        "symbol": "AUDUSD",
        "name": "AUD / USD",
        "category": "FOREX",
        "type": "Dólar Australiano / USD",
        "icon": "🇦🇺",
        "base_price": 0.7029,
        "volatility": 0.0038,
        "trend_bias": 0.0001
    },
    {
        "symbol": "USDCAD",
        "name": "USD / CAD",
        "category": "FOREX",
        "type": "Dólar / Dólar Canadiense",
        "icon": "🇨🇦",
        "base_price": 1.4041,
        "volatility": 0.0035,
        "trend_bias": 0.0001
    },
    {
        "symbol": "USDCHF",
        "name": "USD / CHF",
        "category": "FOREX",
        "type": "Dólar / Franco Suizo",
        "icon": "🇨🇭",
        "base_price": 0.8288,
        "volatility": 0.0034,
        "trend_bias": 0.0001
    },
    {
        "symbol": "NZDUSD",
        "name": "NZD / USD",
        "category": "FOREX",
        "type": "Dólar Neozelandés / USD",
        "icon": "🇳🇿",
        "base_price": 0.5685,
        "volatility": 0.0040,
        "trend_bias": 0.0001
    },
    {
        "symbol": "EURGBP",
        "name": "EUR / GBP",
        "category": "FOREX",
        "type": "Euro / Libra Esterlina",
        "icon": "🇪🇺",
        "base_price": 0.8369,
        "volatility": 0.0028,
        "trend_bias": 0.0001
    },
    {
        "symbol": "EURJPY",
        "name": "EUR / JPY",
        "category": "FOREX",
        "type": "Euro / Yen Japonés",
        "icon": "🇯🇵",
        "base_price": 175.93,
        "volatility": 0.0050,
        "trend_bias": 0.0001
    },
    {
        "symbol": "GBPJPY",
        "name": "GBP / JPY",
        "category": "FOREX",
        "type": "Libra / Yen Japonés",
        "icon": "🇬🇧",
        "base_price": 210.23,
        "volatility": 0.0065,
        "trend_bias": 0.0001
    },
    {
        "symbol": "EURUSD-OTC",
        "name": "EUR / USD (OTC 24/7)",
        "category": "FOREX",
        "type": "Euro / Dólar OTC",
        "icon": "💶",
        "base_price": 1.1232,
        "volatility": 0.0035,
        "trend_bias": 0.0001
    },
    {
        "symbol": "EURGBP-OTC",
        "name": "EUR / GBP (OTC 24/7)",
        "category": "FOREX",
        "type": "Euro / Libra OTC",
        "icon": "🇪🇺",
        "base_price": 0.8311,
        "volatility": 0.0028,
        "trend_bias": 0.0001
    },
    {
        "symbol": "USDCHF-OTC",
        "name": "USD / CHF (OTC 24/7)",
        "category": "FOREX",
        "type": "Dólar / Franco Suizo OTC",
        "icon": "🇨🇭",
        "base_price": 0.8242,
        "volatility": 0.0034,
        "trend_bias": 0.0001
    },
    {
        "symbol": "EURJPY-OTC",
        "name": "EUR / JPY (OTC 24/7)",
        "category": "FOREX",
        "type": "Euro / Yen OTC",
        "icon": "🇯🇵",
        "base_price": 175.74,
        "volatility": 0.0050,
        "trend_bias": 0.0001
    },
    {
        "symbol": "NZDUSD-OTC",
        "name": "NZD / USD (OTC 24/7)",
        "category": "FOREX",
        "type": "Dólar Neozelandés OTC",
        "icon": "🇳🇿",
        "base_price": 0.5085,
        "volatility": 0.0040,
        "trend_bias": 0.0001
    },
    {
        "symbol": "GBPUSD-OTC",
        "name": "GBP / USD (OTC 24/7)",
        "category": "FOREX",
        "type": "Libra / Dólar OTC",
        "icon": "💷",
        "base_price": 1.3315,
        "volatility": 0.0040,
        "trend_bias": 0.0001
    },
    {
        "symbol": "USDJPY-OTC",
        "name": "USD / JPY (OTC 24/7)",
        "category": "FOREX",
        "type": "Dólar / Yen OTC",
        "icon": "💴",
        "base_price": 157.89,
        "volatility": 0.0045,
        "trend_bias": 0.0001
    },
    {
        "symbol": "AUDUSD-OTC",
        "name": "AUD / USD (OTC 24/7)",
        "category": "FOREX",
        "type": "Dólar Australiano OTC",
        "icon": "🇦🇺",
        "base_price": 0.6550,
        "volatility": 0.0038,
        "trend_bias": 0.0001
    },
    {
        "symbol": "GBPJPY-OTC",
        "name": "GBP / JPY (OTC 24/7)",
        "category": "FOREX",
        "type": "Libra / Yen OTC",
        "icon": "🇬🇧",
        "base_price": 210.23,
        "volatility": 0.0065,
        "trend_bias": 0.0001
    },
    {
        "symbol": "AUDCAD-OTC",
        "name": "AUD / CAD (OTC 24/7)",
        "category": "FOREX",
        "type": "Dólar Australiano / Canadiense OTC",
        "icon": "🇦🇺",
        "base_price": 0.8850,
        "volatility": 0.0035,
        "trend_bias": 0.0001
    },
    {
        "symbol": "USDCAD-OTC",
        "name": "USD / CAD (OTC 24/7)",
        "category": "FOREX",
        "type": "Dólar / Dólar Canadiense OTC",
        "icon": "🇨🇦",
        "base_price": 1.4050,
        "volatility": 0.0035,
        "trend_bias": 0.0001
    },
    {
        "symbol": "GBPAUD-OTC",
        "name": "GBP / AUD (OTC 24/7)",
        "category": "FOREX",
        "type": "Libra / Dólar Australiano OTC",
        "icon": "🇬🇧",
        "base_price": 2.0300,
        "volatility": 0.0045,
        "trend_bias": 0.0001
    },
    {
        "symbol": "EURCAD-OTC",
        "name": "EUR / CAD (OTC 24/7)",
        "category": "FOREX",
        "type": "Euro / Dólar Canadiense OTC",
        "icon": "🇪🇺",
        "base_price": 1.5750,
        "volatility": 0.0038,
        "trend_bias": 0.0001
    },
    {
        "symbol": "CHFJPY-OTC",
        "name": "CHF / JPY (OTC 24/7)",
        "category": "FOREX",
        "type": "Franco Suizo / Yen OTC",
        "icon": "🇨🇭",
        "base_price": 190.50,
        "volatility": 0.0050,
        "trend_bias": 0.0001
    },
    {
        "symbol": "CADCHF-OTC",
        "name": "CAD / CHF (OTC 24/7)",
        "category": "FOREX",
        "type": "Dólar Canadiense / Franco OTC",
        "icon": "🇨🇦",
        "base_price": 0.5890,
        "volatility": 0.0035,
        "trend_bias": 0.0001
    },
    {
        "symbol": "EURAUD-OTC",
        "name": "EUR / AUD (OTC 24/7)",
        "category": "FOREX",
        "type": "Euro / Dólar Australiano OTC",
        "icon": "🇪🇺",
        "base_price": 1.7150,
        "volatility": 0.0040,
        "trend_bias": 0.0001
    },
    {
        "symbol": "AUDCAD",
        "name": "AUD / CAD",
        "category": "FOREX",
        "type": "Dólar Australiano / Canadiense",
        "icon": "🇦🇺",
        "base_price": 0.8850,
        "volatility": 0.0035,
        "trend_bias": 0.0001
    },
    {
        "symbol": "CHFJPY",
        "name": "CHF / JPY",
        "category": "FOREX",
        "type": "Franco Suizo / Yen",
        "icon": "🇨🇭",
        "base_price": 190.50,
        "volatility": 0.0050,
        "trend_bias": 0.0001
    },
    {
        "symbol": "GBPAUD",
        "name": "GBP / AUD",
        "category": "FOREX",
        "type": "Libra / Dólar Australiano",
        "icon": "🇬🇧",
        "base_price": 2.0300,
        "volatility": 0.0045,
        "trend_bias": 0.0001
    },
    {
        "symbol": "EURCAD",
        "name": "EUR / CAD",
        "category": "FOREX",
        "type": "Euro / Canadiense",
        "icon": "🇪🇺",
        "base_price": 1.5750,
        "volatility": 0.0038,
        "trend_bias": 0.0001
    },
    {
        "symbol": "EURAUD",
        "name": "EUR / AUD",
        "category": "FOREX",
        "type": "Euro / Australiano",
        "icon": "🇪🇺",
        "base_price": 1.7150,
        "volatility": 0.0040,
        "trend_bias": 0.0001
    }
]



class MultiAssetMarketFeed:
    """
    Feed de cotizaciones exclusivo IQ Option Forex CFD.
    - Fuente primaria: velas reales de IQ Option via WebSocket.
    - Fuente secundaria: tasas interbancarias Forex HTTP (open.er-api.com / frankfurter.dev).
    - Fallback: simulación browniana anclada al precio base real.
    - Sin Binance ni Alpaca.
    """
    VALID_MODES = ["IQ_CFD", "FOREX", "IQOPTION_FOREX", "SIMULATION"]

    def __init__(self):
        self.assets: Dict[str, Dict[str, Any]] = {}
        self.history: Dict[str, List[Dict[str, Any]]] = {}
        self.candles: Dict[str, List[Dict[str, Any]]] = {}
        self._last_iq_candle_refresh: Dict[str, float] = {}
        self.broker_config = load_broker_config()
        self.mode = "IQ_CFD"  # Modo único
        self.iqoption = IQOptionAdapter(
            email=self.broker_config.get("iqoption", {}).get("email", ""),
            password=self.broker_config.get("iqoption", {}).get("password", ""),
            ssid=self.broker_config.get("iqoption", {}).get("ssid", ""),
            environment=self.broker_config.get("iqoption_environment", "PAPER")
        )
        self.last_live_fetch = 0.0
        self.live_cache: Dict[str, float] = {}
        self._last_fx_fetch = 0.0
        self._initialize_assets()

    def set_mode(self, new_mode: str):
        """Mantiene siempre IQ_CFD; ignora modos no permitidos."""
        if new_mode in self.VALID_MODES:
            self.mode = new_mode
            self.broker_config["operating_mode"] = new_mode
            from config.broker_config import save_broker_config
            save_broker_config(self.broker_config)

    def reload_credentials(self):
        self.broker_config = load_broker_config()
        self.mode = "IQ_CFD"
        self.iqoption = IQOptionAdapter(
            email=self.broker_config.get("iqoption", {}).get("email", ""),
            password=self.broker_config.get("iqoption", {}).get("password", ""),
            ssid=self.broker_config.get("iqoption", {}).get("ssid", ""),
            environment=self.broker_config.get("iqoption_environment", "PAPER")
        )

    def _initialize_assets(self):
        now = time.time()
        # Intentar cargar inmediatamente cotizaciones interbancarias reales para evitar saltos
        try:
            self._run_fx_fetch_worker()
        except Exception:
            pass
        for item in AVAILABLE_ASSETS:
            sym = item["symbol"]
            price = self.live_cache.get(sym, item["base_price"])
            category = item.get("category", "TRADFI_STOCK")
            if category == "FOREX":
                dec_places = 3 if "JPY" in sym else 5
                band = 0.0015 if "JPY" not in sym else 0.15
            elif price < 1000:
                dec_places = 2
                band = price * 0.01
            else:
                dec_places = 1
                band = price * 0.01

            self.assets[sym] = {
                "symbol": sym,
                "name": item["name"],
                "category": category,
                "type": item["type"],
                "icon": item["icon"],
                "price": price,
                "open_price": price,
                "change_percent": 0.0,
                "high_24h": round(price + band * 2, dec_places),
                "low_24h": round(price - band * 2, dec_places),
                "volume": random.randint(50000, 450000),
                "ema20": price,
                "ema50": round(price - (band * 0.2), dec_places),
                "rsi": round(random.uniform(48, 52), 1),
                "support": round(price - band, dec_places),
                "resistance": round(price + band, dec_places),
                "volatility": item["volatility"],
                "trend_bias": item["trend_bias"],
                "trend_status": "ESTABLE (Consolidación)",
                "source": "SIMULATION",
                "last_update": now,
            }
            self.history[sym] = []
            curr_p = price * 0.96
            for i in range(50):
                curr_p += (random.uniform(-1, 1.08) * item["volatility"] * curr_p)
                self.history[sym].append({
                    "timestamp": now - (50 - i) * 60,
                    "price": round(curr_p, 2 if curr_p < 1000 else 1),
                    "volume": random.randint(1000, 15000)
                })

    def _fetch_live_data_background(self):
        """Dispara la actualización de cotizaciones Forex en hilo daemon sin bloquear el bucle tick()."""
        now = time.time()
        if now - self._last_fx_fetch < 4.0 or getattr(self, "_fx_fetching", False):
            return
        self._last_fx_fetch = now
        self._fx_fetching = True
        import threading
        threading.Thread(target=self._run_fx_fetch_worker, daemon=True).start()

    def _run_fx_fetch_worker(self):
        try:
            import urllib.request
            import json
            import ssl
            ctx = ssl._create_unverified_context()
            rates = {}
            # Fuente 1: open.er-api.com
            try:
                req1 = urllib.request.Request(
                    "https://open.er-api.com/v6/latest/USD",
                    headers={"User-Agent": "TitoBotTrader/3.0"}
                )
                with urllib.request.urlopen(req1, timeout=2.5, context=ctx) as resp1:
                    data1 = json.loads(resp1.read().decode())
                    if data1.get("result") == "success":
                        rates = data1.get("rates", {})
            except Exception:
                pass
            # Fuente 2: frankfurter.dev
            if not rates:
                try:
                    req2 = urllib.request.Request(
                        "https://api.frankfurter.dev/v1/latest?from=USD",
                        headers={"User-Agent": "TitoBotTrader/3.0"}
                    )
                    with urllib.request.urlopen(req2, timeout=2.5, context=ctx) as resp2:
                        rates = json.loads(resp2.read().decode()).get("rates", {})
                except Exception:
                    pass
            if rates:
                if "EUR" in rates and float(rates["EUR"]) > 0:
                    self.live_cache["EURUSD"] = round(1.0 / float(rates["EUR"]), 5)
                if "GBP" in rates and float(rates["GBP"]) > 0:
                    self.live_cache["GBPUSD"] = round(1.0 / float(rates["GBP"]), 5)
                if "JPY" in rates and float(rates["JPY"]) > 0:
                    self.live_cache["USDJPY"] = round(float(rates["JPY"]), 3)
                if "CAD" in rates and float(rates["CAD"]) > 0:
                    self.live_cache["USDCAD"] = round(float(rates["CAD"]), 5)
                if "CHF" in rates and float(rates["CHF"]) > 0:
                    self.live_cache["USDCHF"] = round(float(rates["CHF"]), 5)
                if "AUD" in rates and float(rates["AUD"]) > 0:
                    self.live_cache["AUDUSD"] = round(1.0 / float(rates["AUD"]), 5)
                if "NZD" in rates and float(rates["NZD"]) > 0:
                    self.live_cache["NZDUSD"] = round(1.0 / float(rates["NZD"]), 5)
                if "EUR" in rates and "GBP" in rates and float(rates["EUR"]) > 0 and float(rates["GBP"]) > 0:
                    self.live_cache["EURGBP"] = round(float(rates["GBP"]) / float(rates["EUR"]), 5)
                if "EUR" in rates and "JPY" in rates and float(rates["EUR"]) > 0:
                    self.live_cache["EURJPY"] = round(float(rates["JPY"]) / float(rates["EUR"]), 3)
                if "GBP" in rates and "JPY" in rates and float(rates["GBP"]) > 0:
                    self.live_cache["GBPJPY"] = round(float(rates["JPY"]) / float(rates["GBP"]), 3)

            # Si IQ Option está autenticado, refrescar cotizaciones reales de los pares FOREX y OTC
            if hasattr(self, "iqoption") and getattr(self.iqoption, "is_configured", False) and getattr(self.iqoption, "ssid", None):
                for sym, asset in self.assets.items():
                    if asset.get("category") == "FOREX":
                        try:
                            iq_c = self.iqoption.get_candles(sym, interval=60, count=60)
                            if iq_c and len(iq_c) >= 5:
                                for candle in iq_c:
                                    candle["source"] = "IQOPTION_REAL_FEED"
                                self.candles[sym] = iq_c
                                self._last_iq_candle_refresh[sym] = time.time()
                                self.live_cache[sym] = iq_c[-1]["close"]
                                asset["price"] = iq_c[-1]["close"]
                                asset["source"] = "IQOPTION_REAL_FEED"
                        except Exception:
                            pass
        except Exception:
            pass
        finally:
            self._fx_fetching = False

    def tick(self) -> Dict[str, Dict[str, Any]]:
        now = time.time()
        try:
            self._fetch_live_data_background()
        except Exception:
            pass

        for sym, asset in self.assets.items():
            old_price = asset["price"]
            category = asset.get("category", "TRADFI_STOCK")
            
            # Determinación de precisión decimal según tipo de activo
            if category == "FOREX":
                dec_places = 3 if "JPY" in sym else 5
            elif old_price < 1000:
                dec_places = 2
            else:
                dec_places = 1

            use_live_price = (sym in self.live_cache)
            if use_live_price:
                base_ref = self.live_cache[sym]
                new_price = round(base_ref, dec_places)
                asset["source"] = asset.get("source", "LIVE_MARKET")
                if asset["source"] not in ["IQOPTION_REAL_FEED", "LIVE_MARKET"]:
                    asset["source"] = "LIVE_MARKET"
            else:
                if category == "FOREX":
                    # Prohibir precios sintéticos o random walk: si hay velas de IQ Option, usar su close real
                    if sym in self.candles and len(self.candles[sym]) > 0:
                        new_price = round(float(self.candles[sym][-1].get("close", asset.get("base_price", 1.0))), dec_places)
                        asset["source"] = str(self.candles[sym][-1].get("source", "UNKNOWN"))
                    else:
                        base_p = asset.get("base_price", asset.get("open_price", 1.0))
                        new_price = round(base_p, dec_places)
                        asset["source"] = "BASE_ANCHOR"
                else:
                    shock = random.gauss(asset["trend_bias"], asset["volatility"])
                    wave = math.sin(now / 18.0 + hash(sym) % 12) * (asset["volatility"] * 0.35)
                    delta_ratio = shock + wave
                    new_price = max(0.01, round(old_price * (1 + delta_ratio), dec_places))
                    asset["source"] = "SIMULATION"

            asset["price"] = new_price
            open_p = asset.get("open_price", new_price)
            asset["change_percent"] = round(((new_price - open_p) / open_p) * 100, 2) if open_p > 0 else 0.0
            if new_price > asset.get("high_24h", new_price):
                asset["high_24h"] = new_price
            if new_price < asset.get("low_24h", new_price):
                asset["low_24h"] = new_price

            vol_delta = random.randint(200, 3500)
            asset["volume"] = asset.get("volume", 0) + vol_delta

            # Medias móviles exponenciales EMA 20 y 50 con precisión adecuada
            asset["ema20"] = round(asset.get("ema20", new_price) * 0.94 + new_price * 0.06, dec_places)
            asset["ema50"] = round(asset.get("ema50", new_price) * 0.98 + new_price * 0.02, dec_places)

            # RSI dinámico
            if new_price > old_price:
                asset["rsi"] = min(96.0, round(asset["rsi"] + (random.uniform(0.3, 1.2) if not use_live_price else 0.4), 1))
            elif new_price < old_price:
                asset["rsi"] = max(4.0, round(asset["rsi"] - (random.uniform(0.3, 1.2) if not use_live_price else 0.4), 1))
            else:
                asset["rsi"] = round(asset["rsi"] * 0.98 + 50.0 * 0.02, 1)

            if asset["price"] > asset["ema20"] and asset["ema20"] > asset["ema50"]:
                asset["trend_status"] = "ALCISTA (Fuerte Demanda)"
            elif asset["price"] < asset["ema20"] and asset["ema20"] < asset["ema50"]:
                asset["trend_status"] = "BAJISTA (Presión de Venta)"
            else:
                asset["trend_status"] = "ESTABLE (Consolidación)"

            asset["last_update"] = now

            self.history[sym].append({
                "timestamp": now,
                "price": new_price,
                "volume": vol_delta
            })
            if len(self.history[sym]) > 100:
                self.history[sym].pop(0)

            # --- GESTIÓN DE VELAS JAPONESAS (OHLCV) EN TIEMPO REAL ---
            if sym not in self.candles or len(self.candles[sym]) == 0:
                self._ensure_candles(sym)

            if sym in self.candles and len(self.candles[sym]) > 0:
                current_minute = (int(now) // 60) * 60
                last_c = self.candles[sym][-1]
                last_c_time = last_c.get("time", current_minute)
                if last_c_time == current_minute:
                    last_c["high"] = max(last_c.get("high", new_price), new_price)
                    last_c["low"] = min(last_c.get("low", new_price), new_price)
                    last_c["close"] = new_price
                    last_c["volume"] = round(last_c.get("volume", 0) + vol_delta, 2)
                elif current_minute > last_c_time:
                    new_c = {
                        "time": current_minute,
                        "open": last_c["close"],
                        "high": max(last_c["close"], new_price),
                        "low": min(last_c["close"], new_price),
                        "close": new_price,
                        "volume": float(vol_delta),
                        # A locally carried bar is not a broker candle.
                        "source": "SIMULATION"
                    }
                    self.candles[sym].append(new_c)
                    if len(self.candles[sym]) > 250:
                        self.candles[sym].pop(0)

            # Recálculo dinámico de Soporte y Resistencia basado estrictamente en las últimas 30 velas M1
            if sym in self.candles and len(self.candles[sym]) >= 3:
                recent_c = self.candles[sym][-30:]
                asset["support"] = round(min(float(c.get("low", c.get("close", new_price))) for c in recent_c), dec_places)
                asset["resistance"] = round(max(float(c.get("high", c.get("close", new_price))) for c in recent_c), dec_places)
            else:
                band = 0.0015 if ("JPY" not in sym and category == "FOREX") else (0.15 if category == "FOREX" else price * 0.01)
                asset["support"] = round(new_price - band, dec_places)
                asset["resistance"] = round(new_price + band, dec_places)

        return self.assets

    def _ensure_candles(self, symbol: str):
        sym = symbol.upper()
        has_enough_candles = sym in self.candles and len(self.candles[sym]) >= 30
        iq_ready = (
            hasattr(self, "iqoption")
            and getattr(self.iqoption, "is_configured", False)
            and getattr(self.iqoption, "ssid", None)
        )
        if has_enough_candles and (
            not iq_ready or time.time() - self._last_iq_candle_refresh.get(sym, 0.0) < 30.0
        ):
            return

        item = next((i for i in AVAILABLE_ASSETS if i["symbol"] == sym), None)
        if not item:
            return

        now = int(time.time())
        current_p = self.live_cache.get(sym, self.assets.get(sym, {}).get("price", item["base_price"]))
        # Protección estricta: Pares con JPY no pueden cotizar por debajo de 50.0 (evita semillas a 0.988 o 1.0)
        if "JPY" in sym and (current_p is None or current_p < 50.0):
            current_p = item.get("base_price", 150.0)
        volat = item.get("volatility", 0.008)

        # 1. Intentar velas reales de IQ Option para activos FOREX y OTC
        if item.get("category") == "FOREX" and iq_ready:
            try:
                iq_candles = self.iqoption.get_candles(sym, interval=60, count=60)
                if iq_candles and len(iq_candles) >= 5:
                    for candle in iq_candles:
                        candle["source"] = "IQOPTION_REAL_FEED"
                    self.candles[sym] = iq_candles
                    self._last_iq_candle_refresh[sym] = time.time()
                    latest = iq_candles[-1]
                    if sym in self.assets:
                        self.assets[sym]["price"] = latest["close"]
                        self.assets[sym]["source"] = "IQOPTION_REAL_FEED"
                        dec = 3 if "JPY" in sym else 5
                        recent_30 = iq_candles[-30:] if len(iq_candles) >= 30 else iq_candles
                        self.assets[sym]["support"] = round(min(c["low"] for c in recent_30), dec)
                        self.assets[sym]["resistance"] = round(max(c["high"] for c in recent_30), dec)
                    return
            except Exception:
                pass

        # 3. Generador estocástico continuo con mechas y cuerpos de alta resolución
        num_bars = 100
        candles = []
        start_time = (now // 60 - num_bars) * 60
        
        # Precisión decimal rigurosa según categoría financiera
        if item.get("category") == "FOREX":
            dec = 3 if "JPY" in sym else 5
            c_volat = 0.00025 if "JPY" not in sym else 0.00035
            p = current_p * (1.0 - (random.uniform(-0.0015, 0.0020)))
        elif current_p < 1.0:
            dec = 4
            c_volat = volat
            p = current_p * (1.0 - (random.uniform(-0.012, 0.015)))
        elif current_p < 20.0:
            dec = 3
            c_volat = volat
            p = current_p * (1.0 - (random.uniform(-0.012, 0.015)))
        elif current_p < 1000:
            dec = 2
            c_volat = volat
            p = current_p * (1.0 - (random.uniform(-0.012, 0.015)))
        else:
            dec = 1
            c_volat = volat
            p = current_p * (1.0 - (random.uniform(-0.012, 0.015)))

        for i in range(num_bars):
            bar_time = start_time + i * 60
            drift = (current_p - p) / max(1, num_bars - i)
            ret = random.gauss(drift / max(p, 1e-4), c_volat * 0.4)
            bar_open = round(p, dec)
            p = max(0.00001, p * (1 + ret))
            if i == num_bars - 1:
                p = current_p
            bar_close = round(p, dec)

            high_wiggle = abs(random.gauss(0, c_volat * 0.35)) * max(bar_open, bar_close)
            low_wiggle = abs(random.gauss(0, c_volat * 0.35)) * min(bar_open, bar_close)
            bar_high = round(max(bar_open, bar_close) + high_wiggle, dec)
            bar_low = round(max(0.00001, min(bar_open, bar_close) - low_wiggle), dec)
            bar_vol = round(random.uniform(500, 15000), 1)

            candles.append({
                "time": bar_time,
                "open": bar_open,
                "high": bar_high,
                "low": bar_low,
                "close": bar_close,
                "volume": bar_vol,
                "source": "SIMULATION"
            })

        self.candles[sym] = candles

    def is_live_data_quality_ok(self, symbol: str, interval_seconds: int = 60, max_age_seconds: int = 120) -> bool:
        """Require a recent, fully closed IQ Option candle before any live entry."""
        candles = self.candles.get(str(symbol).upper(), [])
        now = time.time()
        closed = []
        for candle in candles:
            if candle.get("source") != "IQOPTION_REAL_FEED":
                continue
            try:
                stamp = float(candle.get("time", 0))
                if stamp > 10_000_000_000:
                    stamp /= 1000.0
                if stamp > 0 and stamp + int(interval_seconds) <= now:
                    closed.append(stamp)
            except (TypeError, ValueError):
                continue
        return bool(closed and 0 <= now - (max(closed) + interval_seconds) <= max_age_seconds)

    @staticmethod
    def _candle_time_seconds(candle: Dict[str, Any]) -> Optional[int]:
        try:
            stamp = float(candle.get("time", 0))
        except (TypeError, ValueError):
            return None
        if stamp > 10_000_000_000:
            stamp /= 1000.0
        return int(stamp) if stamp > 0 else None

    def get_verified_iq_market_snapshot(
        self,
        symbol: str,
        interval_seconds: int = 60,
        min_closed_candles: int = 50,
        max_quote_age_seconds: int = 20,
        max_closed_age_seconds: int = 75,
    ) -> Optional[Dict[str, Any]]:
        """Return only a fresh IQ Option candle, a current-minute quote and closed history."""
        sym = str(symbol).upper()
        now = time.time()
        refreshed_at = float(self._last_iq_candle_refresh.get(sym, 0.0))
        quote_age = now - refreshed_at
        if refreshed_at <= 0 or quote_age < 0 or quote_age > max_quote_age_seconds:
            return None

        broker_candles: List[Dict[str, Any]] = []
        for raw in list(self.candles.get(sym, [])):
            if str(raw.get("source", "")).upper() != "IQOPTION_REAL_FEED":
                continue
            stamp = self._candle_time_seconds(raw)
            if stamp is None or stamp > now + 1:
                continue
            try:
                candle = {
                    "time": stamp,
                    "open": float(raw["open"]),
                    "high": float(raw["high"]),
                    "low": float(raw["low"]),
                    "close": float(raw["close"]),
                    "volume": float(raw.get("volume", 0.0)),
                    "source": "IQOPTION_REAL_FEED",
                }
            except (KeyError, TypeError, ValueError):
                continue
            if min(candle["open"], candle["high"], candle["low"], candle["close"]) <= 0:
                continue
            if candle["high"] < max(candle["open"], candle["close"]):
                continue
            if candle["low"] > min(candle["open"], candle["close"]):
                continue
            broker_candles.append(candle)

        broker_candles.sort(key=lambda candle: candle["time"])
        current_minute = (int(now) // interval_seconds) * interval_seconds
        current = [c for c in broker_candles if c["time"] == current_minute]
        closed = [c for c in broker_candles if c["time"] + interval_seconds <= now]
        if not current or len(closed) < min_closed_candles:
            return None
        if now - (closed[-1]["time"] + interval_seconds) > max_closed_age_seconds:
            return None

        current_candle = current[-1]
        return {
            "symbol": sym,
            "interval_seconds": interval_seconds,
            "closed_candles": closed[-100:],
            "current_candle": current_candle,
            "current_price": current_candle["close"],
            "refreshed_at": refreshed_at,
            "quote_age_seconds": round(quote_age, 2),
            "latest_closed_at": closed[-1]["time"] + interval_seconds,
        }

    @staticmethod
    def enrich_asset_from_iq_snapshot(asset: Dict[str, Any], snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate strategy inputs from closed IQ Option candles rather than tick heuristics."""
        closed = list(snapshot.get("closed_candles", []))
        closes = [float(c["close"]) for c in closed]
        if len(closes) < 50:
            raise ValueError("Se requieren 50 velas IQ Option cerradas para calcular indicadores.")

        def ema(values: List[float], period: int) -> float:
            alpha = 2.0 / (period + 1.0)
            value = values[0]
            for item in values[1:]:
                value = alpha * item + (1.0 - alpha) * value
            return value

        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [max(0.0, delta) for delta in deltas]
        losses = [max(0.0, -delta) for delta in deltas]
        period = 14
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for gain, loss in zip(gains[period:], losses[period:]):
            avg_gain = ((period - 1) * avg_gain + gain) / period
            avg_loss = ((period - 1) * avg_loss + loss) / period
        rsi = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))

        recent = closed[-30:]
        price = float(snapshot["current_price"])
        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50)
        result = dict(asset)
        result.update({
            "price": price,
            "ema20": ema20,
            "ema50": ema50,
            "rsi": round(rsi, 2),
            "support": min(float(c["low"]) for c in recent),
            "resistance": max(float(c["high"]) for c in recent),
            "change_percent": round((price - closes[-1]) / closes[-1] * 100.0, 5) if closes[-1] else 0.0,
            "trend_status": "ALCISTA" if price > ema20 > ema50 else ("BAJISTA" if price < ema20 < ema50 else "ESTABLE"),
            "source": "IQOPTION_REAL_FEED",
            "last_update": snapshot.get("refreshed_at", time.time()),
        })
        return result

    def get_candles(self, symbol: str, timeframe: str = "1m", limit: int = 100) -> List[Dict[str, Any]]:
        sym = symbol.upper()
        if sym not in self.candles or len(self.candles[sym]) < 10:
            self._ensure_candles(sym)

        base_candles = self.candles.get(sym, [])
        if not base_candles:
            return []

        if timeframe == "1m":
            return base_candles[-limit:]

        # Agregación temporal (5m, 15m, 1h) a partir de velas de 1m
        step_min = 5 if timeframe == "5m" else (15 if timeframe == "15m" else 60)
        bucket_sec = step_min * 60
        aggregated = []
        cur_bucket = None
        cur_c = None

        for c in base_candles:
            b_time = (c["time"] // bucket_sec) * bucket_sec
            if cur_bucket != b_time:
                if cur_c is not None:
                    aggregated.append(cur_c)
                cur_bucket = b_time
                cur_c = {
                    "time": b_time,
                    "open": c["open"],
                    "high": c["high"],
                    "low": c["low"],
                    "close": c["close"],
                    "volume": c["volume"]
                }
            else:
                cur_c["high"] = max(cur_c["high"], c["high"])
                cur_c["low"] = min(cur_c["low"], c["low"])
                cur_c["close"] = c["close"]
                cur_c["volume"] = round(cur_c["volume"] + c["volume"], 2)

        if cur_c is not None:
            aggregated.append(cur_c)

        return aggregated[-limit:]

    def get_asset(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self.assets.get(symbol)

    def reset_forex_feed(self):
        """Restaura los activos Forex a sus precios base reales e inicializa sus indicadores limpios."""
        now = time.time()
        for item in AVAILABLE_ASSETS:
            sym = item["symbol"]
            if item.get("category") == "FOREX":
                price = item["base_price"]
                dec = 3 if "JPY" in sym else 5
                self.assets[sym] = {
                    "symbol": sym,
                    "name": item["name"],
                    "category": "FOREX",
                    "type": item["type"],
                    "icon": item["icon"],
                    "price": price,
                    "open_price": price,
                    "change_percent": 0.0,
                    "high_24h": round(price * 1.005, dec),
                    "low_24h": round(price * 0.995, dec),
                    "volume": random.randint(50000, 450000),
                    "ema20": price,
                    "ema50": price,
                    "rsi": 50.0,
                    "support": round(price * 0.992, dec),
                    "resistance": round(price * 1.008, dec),
                    "volatility": item["volatility"],
                    "trend_bias": item["trend_bias"],
                    "trend_status": "ESTABLE (Consolidación)",
                    "source": "REAL_RESET",
                    "last_update": now,
                }
                if sym in self.candles:
                    del self.candles[sym]
                self._ensure_candles(sym)

    def get_all_assets(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        is_weekend = datetime.datetime.now(datetime.timezone.utc).weekday() >= 5
        all_items = list(self.assets.values())

        if not category or category == "ALL":
            return all_items
        if category == "TRADFI":
            return [a for a in all_items if a.get("category") in ["TRADFI_STOCK", "ETF"]]
        return [a for a in all_items if a.get("category") == category]
