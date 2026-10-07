import time
import random
import math
import threading
from typing import Dict, List, Any, Optional
from config.broker_config import load_broker_config
from execution.alpaca_adapter import AlpacaAdapter
from execution.binance_adapter import BinanceAdapter
from execution.iqoption_adapter import IQOptionAdapter

# Catálogo Completo: Wall Street TradFi (Acciones de EE.UU. + ETFs en Binance) + Top Criptomonedas
AVAILABLE_ASSETS = [
    # === ACCIONES TRADFI WALL STREET (Captura Binance TradFi) ===
    {
        "symbol": "META",
        "name": "Meta Platforms, Inc.",
        "category": "TRADFI_STOCK",
        "type": "Redes Sociales / IA & RV",
        "icon": "♾️",
        "base_price": 588.30,
        "volatility": 0.0055,
        "trend_bias": 0.0004
    },
    {
        "symbol": "MU",
        "name": "Micron Technology",
        "category": "TRADFI_STOCK",
        "type": "Memoria / Semiconductores",
        "icon": "💾",
        "base_price": 112.30,
        "volatility": 0.0068,
        "trend_bias": 0.0005
    },
    {
        "symbol": "AMD",
        "name": "Advanced Micro Devices",
        "category": "TRADFI_STOCK",
        "type": "CPUs / GPUs / Data Center",
        "icon": "⚡",
        "base_price": 158.40,
        "volatility": 0.0062,
        "trend_bias": 0.0005
    },
    {
        "symbol": "INTC",
        "name": "Intel Corporation",
        "category": "TRADFI_STOCK",
        "type": "Semiconductores / Fundición",
        "icon": "🔷",
        "base_price": 24.80,
        "volatility": 0.0058,
        "trend_bias": 0.0002
    },
    {
        "symbol": "NVDA",
        "name": "NVIDIA Corp.",
        "category": "TRADFI_STOCK",
        "type": "Líder Global Computación IA",
        "icon": "🟢",
        "base_price": 142.60,
        "volatility": 0.0065,
        "trend_bias": 0.0006
    },
    {
        "symbol": "SNDK",
        "name": "SanDisk Corp.",
        "category": "TRADFI_STOCK",
        "type": "Almacenamiento Flash / Hardware",
        "icon": "🔴",
        "base_price": 78.90,
        "volatility": 0.0052,
        "trend_bias": 0.0003
    },
    {
        "symbol": "TSLA",
        "name": "Tesla Motors",
        "category": "TRADFI_STOCK",
        "type": "Vehículos Autónomos / Robótica",
        "icon": "🚗",
        "base_price": 248.80,
        "volatility": 0.0075,
        "trend_bias": 0.0004
    },
    {
        "symbol": "MSFT",
        "name": "Microsoft Corp.",
        "category": "TRADFI_STOCK",
        "type": "Software / Cloud Azure / OpenAI",
        "icon": "💻",
        "base_price": 428.10,
        "volatility": 0.0035,
        "trend_bias": 0.0003
    },
    {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "category": "TRADFI_STOCK",
        "type": "Hardware / Ecosistema iOS",
        "icon": "🍎",
        "base_price": 224.50,
        "volatility": 0.0038,
        "trend_bias": 0.0003
    },
    {
        "symbol": "AMZN",
        "name": "Amazon.com",
        "category": "TRADFI_STOCK",
        "type": "Cloud AWS / E-Commerce Global",
        "icon": "📦",
        "base_price": 186.40,
        "volatility": 0.0042,
        "trend_bias": 0.0003
    },
    {
        "symbol": "GOOGL",
        "name": "Alphabet (Google)",
        "category": "TRADFI_STOCK",
        "type": "Búsqueda / Gemini IA / Cloud",
        "icon": "🔍",
        "base_price": 162.70,
        "volatility": 0.0040,
        "trend_bias": 0.0003
    },

    # === ETFs DE WALL STREET ===
    {
        "symbol": "SPCX",
        "name": "Space Exploration ETF",
        "category": "ETF",
        "type": "Aeroespacial & Satélites",
        "icon": "🚀",
        "base_price": 32.40,
        "volatility": 0.0048,
        "trend_bias": 0.0003
    },
    {
        "symbol": "SPY",
        "name": "SPDR S&P 500 ETF Trust",
        "category": "ETF",
        "type": "Índice 500 Grandes EE.UU.",
        "icon": "🏛️",
        "base_price": 565.20,
        "volatility": 0.0028,
        "trend_bias": 0.0003
    },
    {
        "symbol": "QQQ",
        "name": "Invesco QQQ NASDAQ 100",
        "category": "ETF",
        "type": "Top 100 Tecnología EE.UU.",
        "icon": "📈",
        "base_price": 485.60,
        "volatility": 0.0038,
        "trend_bias": 0.0004
    },

    # === CRIPTOMONEDAS TOP SPOT ===
    {
        "symbol": "BTC",
        "name": "Bitcoin / USD",
        "category": "CRYPTO",
        "type": "Oro Digital / Reserva Global",
        "icon": "🪙",
        "binance_pair": "BTCUSDT",
        "base_price": 84200.0,
        "volatility": 0.0080,
        "trend_bias": 0.0005
    },
    {
        "symbol": "ETH",
        "name": "Ethereum / USD",
        "category": "CRYPTO",
        "type": "Smart Contracts / DeFi Líder",
        "icon": "🔷",
        "binance_pair": "ETHUSDT",
        "base_price": 2680.0,
        "volatility": 0.0090,
        "trend_bias": 0.0005
    },
    {
        "symbol": "SOL",
        "name": "Solana / USD",
        "category": "CRYPTO",
        "type": "L1 Alta Velocidad & Web3",
        "icon": "🟣",
        "binance_pair": "SOLUSDT",
        "base_price": 116.5,
        "volatility": 0.0110,
        "trend_bias": 0.0006
    },
    {
        "symbol": "BNB",
        "name": "Binance Coin",
        "category": "CRYPTO",
        "type": "Ecosistema Binance & BSC",
        "icon": "🟡",
        "binance_pair": "BNBUSDT",
        "base_price": 777.0,
        "volatility": 0.0085,
        "trend_bias": 0.0004
    },
    {
        "symbol": "XRP",
        "name": "Ripple / USD",
        "category": "CRYPTO",
        "type": "Pagos Bancarios Transfronterizos",
        "icon": "💎",
        "binance_pair": "XRPUSDT",
        "base_price": 1.54,
        "volatility": 0.0120,
        "trend_bias": 0.0005
    },
    {
        "symbol": "DOGE",
        "name": "Dogecoin / USD",
        "category": "CRYPTO",
        "type": "Alta Volatilidad / Momentum",
        "icon": "🐕",
        "binance_pair": "DOGEUSDT",
        "base_price": 0.095,
        "volatility": 0.0160,
        "trend_bias": 0.0007
    },
    {
        "symbol": "ADA",
        "name": "Cardano / USD",
        "category": "CRYPTO",
        "type": "Smart Contracts PoS Revisado",
        "icon": "🔵",
        "binance_pair": "ADAUSDT",
        "base_price": 0.25,
        "volatility": 0.0120,
        "trend_bias": 0.0004
    },
    {
        "symbol": "AVAX",
        "name": "Avalanche / USD",
        "category": "CRYPTO",
        "type": "Subnets / DeFi Escalable",
        "icon": "🔺",
        "binance_pair": "AVAXUSDT",
        "base_price": 10.22,
        "volatility": 0.0130,
        "trend_bias": 0.0006
    },
    {
        "symbol": "LINK",
        "name": "Chainlink / USD",
        "category": "CRYPTO",
        "type": "Oráculos & Conexión TradFi RWA",
        "icon": "🔗",
        "binance_pair": "LINKUSDT",
        "base_price": 13.24,
        "volatility": 0.0120,
        "trend_bias": 0.0005
    },
    {
        "symbol": "NEAR",
        "name": "NEAR Protocol",
        "category": "CRYPTO",
        "type": "IA Descentralizada & Sharding",
        "icon": "🌐",
        "binance_pair": "NEARUSDT",
        "base_price": 4.60,
        "volatility": 0.0150,
        "trend_bias": 0.0007
    },
    # === FOREX & DERIVADOS (IQ Option / Multi-Broker) ===
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
    }
]

class MultiAssetMarketFeed:
    """
    Motor de cotizaciones multiactivo institucional:
    - Modo UNIFIED_TRADFI_CRYPTO / HYBRID: Cobertura simultánea Wall Street + Cripto.
    - Modo TRADFI_WALLSTREET / ALPACA_PAPER: Exclusivo TradFi (acciones y ETFs de Wall Street).
    - Modo BINANCE_CRYPTO: Exclusivo Criptomonedas 24/7.
    - Modo SIMULATION: Motor browniano de alta fidelidad 24/7.
    """
    VALID_MODES = [
        "UNIFIED_TRADFI_CRYPTO", 
        "TRADFI_WALLSTREET", 
        "BINANCE_CRYPTO", 
        "IQOPTION_FOREX",
        "FOREX",
        "HYBRID", 
        "ALPACA_PAPER", 
        "SIMULATION"
    ]

    def __init__(self):
        self.assets: Dict[str, Dict[str, Any]] = {}
        self.history: Dict[str, List[Dict[str, Any]]] = {}
        self.candles: Dict[str, List[Dict[str, Any]]] = {}
        self.broker_config = load_broker_config()
        self.mode = self.broker_config.get("operating_mode", "UNIFIED_TRADFI_CRYPTO")
        if self.mode not in self.VALID_MODES:
            self.mode = "UNIFIED_TRADFI_CRYPTO"

        self.alpaca = AlpacaAdapter(
            api_key=self.broker_config.get("alpaca", {}).get("api_key", ""),
            secret_key=self.broker_config.get("alpaca", {}).get("secret_key", "")
        )
        self.binance = BinanceAdapter(
            api_key=self.broker_config.get("binance", {}).get("api_key", ""),
            secret_key=self.broker_config.get("binance", {}).get("secret_key", "")
        )
        self.iqoption = IQOptionAdapter(
            email=self.broker_config.get("iqoption", {}).get("email", ""),
            password=self.broker_config.get("iqoption", {}).get("password", ""),
            ssid=self.broker_config.get("iqoption", {}).get("ssid", ""),
            environment=self.broker_config.get("iqoption_environment", "PAPER")
        )
        self.last_live_fetch = 0.0
        self.live_cache: Dict[str, float] = {}
        self._initialize_assets()

    def set_mode(self, new_mode: str):
        if new_mode in self.VALID_MODES:
            self.mode = new_mode
            self.broker_config["operating_mode"] = new_mode
            from config.broker_config import save_broker_config
            save_broker_config(self.broker_config)

    def reload_credentials(self):
        self.broker_config = load_broker_config()
        self.mode = self.broker_config.get("operating_mode", "UNIFIED_TRADFI_CRYPTO")
        if self.mode not in self.VALID_MODES:
            self.mode = "UNIFIED_TRADFI_CRYPTO"
        self.alpaca = AlpacaAdapter(
            api_key=self.broker_config.get("alpaca", {}).get("api_key", ""),
            secret_key=self.broker_config.get("alpaca", {}).get("secret_key", "")
        )
        self.binance = BinanceAdapter(
            api_key=self.broker_config.get("binance", {}).get("api_key", ""),
            secret_key=self.broker_config.get("binance", {}).get("secret_key", "")
        )
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
        """Consulta precios reales de Binance y Alpaca en tiempo real"""
        now = time.time()
        if now - self.last_live_fetch < 1.5:
            return
        self.last_live_fetch = now

        # 1. Obtener Cripto real de Binance (datos públicos oficiales en tiempo real para todos los activos cripto)
        crypto_pairs = [item.get("binance_pair") for item in AVAILABLE_ASSETS if item.get("category") == "CRYPTO" and item.get("binance_pair")]
        crypto_data = self.binance.get_public_crypto_prices(crypto_pairs)
        for item in AVAILABLE_ASSETS:
            pair = item.get("binance_pair")
            sym = item.get("symbol")
            if pair and pair in crypto_data and sym:
                self.live_cache[sym] = crypto_data[pair]["price"]

        # 2. Obtener Acciones reales de Alpaca si está configurado
        if self.alpaca.is_configured:
            stock_symbols = [item["symbol"] for item in AVAILABLE_ASSETS if item.get("category") in ["TRADFI_STOCK", "ETF"]]
            stock_data = self.alpaca.get_latest_stock_prices(stock_symbols)
            for sym, p in stock_data.items():
                if p > 0:
                    self.live_cache[sym] = p

    def tick(self) -> Dict[str, Dict[str, Any]]:
        now = time.time()
        try:
            self._fetch_live_data_background()
        except Exception:
            pass

        for sym, asset in self.assets.items():
            old_price = asset["price"]
            category = asset.get("category", "TRADFI_STOCK")
            
            use_live_price = (sym in self.live_cache)
            if use_live_price:
                new_price = self.live_cache[sym]
                asset["source"] = "LIVE_MARKET"
            else:
                # Simulación estocástica browniana dinámica con reversión a la media
                shock = random.gauss(asset["trend_bias"], asset["volatility"])
                wave = math.sin(now / 18.0 + hash(sym) % 12) * (asset["volatility"] * 0.35)
                delta_ratio = shock + wave
                dec_places = 2 if old_price < 1000 else 1
                new_price = max(0.01, round(old_price * (1 + delta_ratio), dec_places))
                asset["source"] = "SIMULATION"

            asset["price"] = new_price
            asset["change_percent"] = round(((new_price - asset["open_price"]) / asset["open_price"]) * 100, 2)
            if new_price > asset["high_24h"]:
                asset["high_24h"] = new_price
            if new_price < asset["low_24h"]:
                asset["low_24h"] = new_price

            vol_delta = random.randint(200, 3500)
            asset["volume"] += vol_delta

            # Medias móviles exponenciales EMA 20 y 50
            asset["ema20"] = round(asset["ema20"] * 0.94 + new_price * 0.06, 2 if new_price < 1000 else 1)
            asset["ema50"] = round(asset["ema50"] * 0.98 + new_price * 0.02, 2 if new_price < 1000 else 1)

            # RSI dinámico
            if new_price > old_price:
                asset["rsi"] = min(96.0, round(asset["rsi"] + (random.uniform(0.4, 1.8) if not use_live_price else 0.6), 1))
            elif new_price < old_price:
                asset["rsi"] = max(4.0, round(asset["rsi"] - (random.uniform(0.4, 1.8) if not use_live_price else 0.6), 1))
            else:
                asset["rsi"] = round(asset["rsi"] * 0.98 + 50.0 * 0.02, 1)

            asset["support"] = round(min(asset["support"], new_price * 0.985), 2 if new_price < 1000 else 1)
            asset["resistance"] = round(max(asset["resistance"], new_price * 1.015), 2 if new_price < 1000 else 1)

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
                if last_c["time"] == current_minute:
                    last_c["high"] = max(last_c["high"], new_price)
                    last_c["low"] = min(last_c["low"], new_price)
                    last_c["close"] = new_price
                    last_c["volume"] = round(last_c["volume"] + vol_delta, 2)
                elif current_minute > last_c["time"]:
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

        # 1. Intentar velas reales de Binance para activos cripto
        if item.get("category") == "CRYPTO" and item.get("binance_pair"):
            try:
                real_klines = self.binance.get_klines(item["binance_pair"], interval="1m", limit=90)
                if real_klines and len(real_klines) > 10:
                    self.candles[sym] = real_klines
                    return
            except Exception:
                pass

        # 2. Intentar velas reales de Alpaca para acciones TradFi y ETFs
        if item.get("category") in ["TRADFI_STOCK", "ETF"] and self.alpaca.is_configured:
            try:
                stock_bars = self.alpaca.get_stock_bars(sym, limit=90)
                if stock_bars and len(stock_bars) > 5:
                    self.candles[sym] = stock_bars
                    return
            except Exception:
                pass

        # 3. Generador estocástico continuo con mechas y cuerpos de alta resolución
        num_bars = 90
        candles = []
        start_time = (now // 60 - num_bars) * 60
        dec = 4 if current_p < 1.0 else (2 if current_p < 1000 else 1)
        p = current_p * (1.0 - (random.uniform(-0.012, 0.015)))

        for i in range(num_bars):
            bar_time = start_time + i * 60
            drift = (current_p - p) / max(1, num_bars - i)
            ret = random.gauss(drift / max(p, 1e-4), volat * 0.4)
            bar_open = round(p, dec)
            p = max(0.0001, p * (1 + ret))
            if i == num_bars - 1:
                p = current_p
            bar_close = round(p, dec)

            high_wiggle = abs(random.gauss(0, volat * 0.35)) * max(bar_open, bar_close)
            low_wiggle = abs(random.gauss(0, volat * 0.35)) * min(bar_open, bar_close)
            bar_high = round(max(bar_open, bar_close) + high_wiggle, dec)
            bar_low = round(max(0.0001, min(bar_open, bar_close) - low_wiggle), dec)
            bar_vol = round(random.uniform(500, 15000) * (current_p if current_p < 5 else 1.0), 2)

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

        # Para cripto con Binance disponible directamente en temporalidades superiores (5m, 15m, 1h)
        item = next((i for i in AVAILABLE_ASSETS if i["symbol"] == sym), None)
        if item and item.get("category") == "CRYPTO" and item.get("binance_pair") and timeframe in ["5m", "15m", "1h"]:
            try:
                b_klines = self.binance.get_klines(item["binance_pair"], interval=timeframe, limit=limit)
                if b_klines and len(b_klines) > 5:
                    return b_klines
            except Exception:
                pass

        # Agregación temporal algorítmica para TradFi o simulación (5m, 15m, 1h)
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

    def get_all_assets(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        if not category or category == "ALL":
            return list(self.assets.values())
        if category == "TRADFI":
            return [a for a in self.assets.values() if a.get("category") in ["TRADFI_STOCK", "ETF"]]
        return [a for a in self.assets.values() if a.get("category") == category]
