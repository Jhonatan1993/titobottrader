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
        "base_price": 1.0850,
        "volatility": 0.0035,
        "trend_bias": 0.0001
    },
    {
        "symbol": "GBPUSD",
        "name": "GBP / USD",
        "category": "FOREX",
        "type": "Libra Esterlina / Dólar",
        "icon": "💷",
        "base_price": 1.2950,
        "volatility": 0.0040,
        "trend_bias": 0.0001
    },
    {
        "symbol": "USDJPY",
        "name": "USD / JPY",
        "category": "FOREX",
        "type": "Dólar / Yen Japonés",
        "icon": "💴",
        "base_price": 152.30,
        "volatility": 0.0045,
        "trend_bias": 0.0001
    },
    {
        "symbol": "AUDUSD",
        "name": "AUD / USD",
        "category": "FOREX",
        "type": "Dólar Australiano / USD",
        "icon": "🇦🇺",
        "base_price": 0.6550,
        "volatility": 0.0038,
        "trend_bias": 0.0001
    },
    {
        "symbol": "USDCAD",
        "name": "USD / CAD",
        "category": "FOREX",
        "type": "Dólar / Dólar Canadiense",
        "icon": "🇨🇦",
        "base_price": 1.3850,
        "volatility": 0.0035,
        "trend_bias": 0.0001
    },
    {
        "symbol": "USDCHF",
        "name": "USD / CHF",
        "category": "FOREX",
        "type": "Dólar / Franco Suizo",
        "icon": "🇨🇭",
        "base_price": 0.8650,
        "volatility": 0.0034,
        "trend_bias": 0.0001
    },
    {
        "symbol": "NZDUSD",
        "name": "NZD / USD",
        "category": "FOREX",
        "type": "Dólar Neozelandés / USD",
        "icon": "🇳🇿",
        "base_price": 0.6050,
        "volatility": 0.0040,
        "trend_bias": 0.0001
    },
    {
        "symbol": "EURGBP",
        "name": "EUR / GBP",
        "category": "FOREX",
        "type": "Euro / Libra Esterlina",
        "icon": "🇪🇺",
        "base_price": 0.8350,
        "volatility": 0.0028,
        "trend_bias": 0.0001
    },
    {
        "symbol": "EURJPY",
        "name": "EUR / JPY",
        "category": "FOREX",
        "type": "Euro / Yen Japonés",
        "icon": "🇯🇵",
        "base_price": 165.20,
        "volatility": 0.0050,
        "trend_bias": 0.0001
    },
    {
        "symbol": "GBPJPY",
        "name": "GBP / JPY",
        "category": "FOREX",
        "type": "Libra / Yen Japonés",
        "icon": "🇬🇧",
        "base_price": 197.80,
        "volatility": 0.0065,
        "trend_bias": 0.0001
    },
    {
        "symbol": "EURUSD-OTC",
        "name": "EUR / USD (OTC 24/7)",
        "category": "FOREX",
        "type": "Euro / Dólar OTC",
        "icon": "🇪🇺",
        "base_price": 1.0850,
        "volatility": 0.0035,
        "trend_bias": 0.0001
    },
    {
        "symbol": "GBPUSD-OTC",
        "name": "GBP / USD (OTC 24/7)",
        "category": "FOREX",
        "type": "Libra / Dólar OTC",
        "icon": "💷",
        "base_price": 1.2950,
        "volatility": 0.0040,
        "trend_bias": 0.0001
    },
    {
        "symbol": "USDJPY-OTC",
        "name": "USD / JPY (OTC 24/7)",
        "category": "FOREX",
        "type": "Dólar / Yen OTC",
        "icon": "💴",
        "base_price": 152.30,
        "volatility": 0.0045,
        "trend_bias": 0.0001
    },
    {
        "symbol": "USDCHF-OTC",
        "name": "USD / CHF (OTC 24/7)",
        "category": "FOREX",
        "type": "Dólar / Franco Suizo OTC",
        "icon": "🇨🇭",
        "base_price": 0.8650,
        "volatility": 0.0034,
        "trend_bias": 0.0001
    },
    {
        "symbol": "EURJPY-OTC",
        "name": "EUR / JPY (OTC 24/7)",
        "category": "FOREX",
        "type": "Euro / Yen OTC",
        "icon": "🇯🇵",
        "base_price": 165.20,
        "volatility": 0.0050,
        "trend_bias": 0.0001
    },
    {
        "symbol": "NZDUSD-OTC",
        "name": "NZD / USD (OTC 24/7)",
        "category": "FOREX",
        "type": "Dólar Neozelandés OTC",
        "icon": "🇳🇿",
        "base_price": 0.6050,
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
        for item in AVAILABLE_ASSETS:
            sym = item["symbol"]
            price = item["base_price"]
            category = item.get("category", "TRADFI_STOCK")
            self.assets[sym] = {
                "symbol": sym,
                "name": item["name"],
                "category": category,
                "type": item["type"],
                "icon": item["icon"],
                "price": price,
                "open_price": price,
                "change_percent": 0.0,
                "high_24h": round(price * 1.02, 2 if price < 1000 else 1),
                "low_24h": round(price * 0.98, 2 if price < 1000 else 1),
                "volume": random.randint(50000, 450000),
                "ema20": price,
                "ema50": price * 0.998,
                "rsi": round(random.uniform(46, 56), 1),
                "support": round(price * 0.97, 2 if price < 1000 else 1),
                "resistance": round(price * 1.03, 2 if price < 1000 else 1),
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
        """Actualiza cotizaciones Forex reales interbancarias desde open.er-api.com / frankfurter.dev."""
        now = time.time()
        if now - self._last_fx_fetch < 4.0:
            return
        self._last_fx_fetch = now
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
                with urllib.request.urlopen(req1, timeout=3.0, context=ctx) as resp1:
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
                    with urllib.request.urlopen(req2, timeout=3.0, context=ctx) as resp2:
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
                # Replicar cotizaciones en vivo a los pares OTC para fines de semana
                for fx_pair in ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "EURJPY", "NZDUSD"]:
                    if fx_pair in self.live_cache:
                        self.live_cache[f"{fx_pair}-OTC"] = self.live_cache[fx_pair]
        except Exception:
            pass

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
                if category == "FOREX":
                    # Micro-ticks de alta frecuencia anclados al precio interbancario real en vivo
                    pip_noise = random.gauss(0, asset.get("volatility", 0.003) * 0.05)
                    new_price = round(base_ref * (1 + pip_noise), dec_places)
                else:
                    new_price = round(base_ref, dec_places)
                asset["source"] = "LIVE_MARKET"
            else:
                if category == "FOREX":
                    base_p = asset.get("base_price", asset.get("open_price", 1.0))
                    # Si el precio anterior colapsó o se disparó más de 50%, recuperamos el base
                    if old_price < base_p * 0.5 or old_price > base_p * 2.0:
                        old_price = base_p
                    reversion = (base_p - old_price) * 0.05
                    shock = random.gauss(reversion, asset["volatility"] * 0.15)
                    new_price = max(base_p * 0.7, round(old_price * (1 + shock), dec_places))
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

            asset["support"] = round(min(asset["support"], new_price * 0.985), dec_places)
            asset["resistance"] = round(max(asset["resistance"], new_price * 1.015), dec_places)

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
                        "volume": float(vol_delta)
                    }
                    self.candles[sym].append(new_c)
                    if len(self.candles[sym]) > 250:
                        self.candles[sym].pop(0)

        return self.assets

    def _ensure_candles(self, symbol: str):
        sym = symbol.upper()
        if sym in self.candles and len(self.candles[sym]) >= 30:
            return

        item = next((i for i in AVAILABLE_ASSETS if i["symbol"] == sym), None)
        if not item:
            return

        now = int(time.time())
        current_p = self.assets.get(sym, {}).get("price", item["base_price"])
        volat = item.get("volatility", 0.008)

        # 1. Intentar velas reales de IQ Option para activos FOREX CFD
        if item.get("category") == "FOREX" and hasattr(self, "iqoption") and getattr(self.iqoption, "is_configured", False) and getattr(self.iqoption, "ssid", None):
            try:
                iq_candles = self.iqoption.get_candles(sym, interval=60, count=60)
                if iq_candles and len(iq_candles) > 10:
                    self.candles[sym] = iq_candles
                    latest = iq_candles[-1]
                    if sym in self.assets:
                        self.assets[sym]["price"] = latest["close"]
                        self.assets[sym]["source"] = "IQOPTION_REAL_FEED"
                    return
            except Exception:
                pass

        # 3. Generador estocástico continuo con mechas y cuerpos de alta resolución
        num_bars = 90
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
                "volume": bar_vol
            })

        self.candles[sym] = candles

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
