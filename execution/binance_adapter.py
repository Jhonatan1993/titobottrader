import time
import hmac
import hashlib
import requests
from urllib.parse import urlencode
from typing import Dict, List, Any, Optional

class BinanceAdapter:
    """
    Adaptador Oficial de Binance con Blindaje de Entornos:
    - Modo Feed Público (Sin riesgo, lectura de precios en tiempo real).
    - Modo Testnet (Paper Trading con broker).
    - Modo Live Real (Dinero real autenticado con llaves API y firma criptográfica).
    """
    def __init__(self, api_key: str = "", secret_key: str = "", testnet: bool = False, live_trading_enabled: bool = False):
        self.api_key = api_key
        self.secret_key = secret_key
        self.testnet = testnet
        self.live_trading_enabled = live_trading_enabled
        self.public_url = "https://api.binance.com/api/v3"
        self.testnet_url = "https://testnet.binance.vision/api/v3"
        self.base_url = self.testnet_url if testnet else self.public_url
        self.is_configured = bool(api_key and secret_key)
        self._cached_ticker_prices: Dict[str, float] = {}
        self._last_ticker_fetch: float = 0.0

    def get_all_ticker_prices(self) -> Dict[str, float]:
        now = time.time()
        if self._cached_ticker_prices and (now - self._last_ticker_fetch) < 10.0:
            return self._cached_ticker_prices
        try:
            url = f"{self.public_url}/ticker/price"
            resp = requests.get(url, timeout=3)
            if resp.status_code == 200:
                self._cached_ticker_prices = {item["symbol"]: float(item["price"]) for item in resp.json() if "symbol" in item and "price" in item}
                self._last_ticker_fetch = now
                return self._cached_ticker_prices
        except Exception:
            pass
        return self._cached_ticker_prices

    def _sign_query(self, params: Dict[str, Any]) -> str:
        params["timestamp"] = int(time.time() * 1000)
        query_string = urlencode(params)
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return f"{query_string}&signature={signature}"

    def get_public_crypto_prices(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Obtiene precios reales en tiempo real de Binance (Sin necesidad de API keys).
        symbols: ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        """
        result = {}
        try:
            formatted_symbols = '["' + '","'.join(symbols) + '"]'
            url = f"{self.public_url}/ticker/24hr?symbols={formatted_symbols}"
            resp = requests.get(url, timeout=4)
            if resp.status_code == 200:
                data = resp.json()
                for item in data:
                    sym = item.get("symbol")
                    result[sym] = {
                        "price": float(item.get("lastPrice", 0.0)),
                        "change_24h": float(item.get("priceChangePercent", 0.0)),
                        "high_24h": float(item.get("highPrice", 0.0)),
                        "low_24h": float(item.get("lowPrice", 0.0)),
                        "volume": float(item.get("volume", 0.0))
                    }
        except Exception:
            pass
        return result

    def get_klines(self, symbol: str, interval: str = "1m", limit: int = 100) -> List[Dict[str, Any]]:
        """
        Obtiene velas históricas (klines) de Binance Spot públicas sin requerir llaves API.
        Retorna lista ordenada cronológicamente de {time, open, high, low, close, volume}.
        """
        try:
            url = f"{self.public_url}/klines?symbol={symbol.upper()}&interval={interval}&limit={limit}"
            resp = requests.get(url, timeout=4)
            if resp.status_code == 200:
                candles = []
                for k in resp.json():
                    candles.append({
                        "time": int(k[0] // 1000),  # Segundos Unix para charts
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4]),
                        "volume": float(k[5])
                    })
                return candles
        except Exception:
            pass
        return []

    def _convert_asset_to_usdt(self, asset_name: str, quantity: float, ticker_prices: Dict[str, float]) -> float:
        if quantity <= 0:
            return 0.0
        clean_sym = asset_name[2:] if (asset_name.startswith("LD") and len(asset_name) > 2) else asset_name
        clean_sym = clean_sym.upper().strip()
        if clean_sym in ["USDT", "USDC", "FDUSD", "BUSD", "DAI", "TUSD"]:
            return quantity
        # 1. Par directo con USDT
        pair_usdt = f"{clean_sym}USDT"
        price = ticker_prices.get(pair_usdt, 0.0)
        if price > 0:
            return quantity * price
        # 2. Pares alternativos con stablecoins
        for alt_quote in ["USDC", "FDUSD"]:
            alt_p = ticker_prices.get(f"{clean_sym}{alt_quote}", 0.0)
            if alt_p > 0:
                return quantity * alt_p
        # 3. Par cruzado con BTC
        btc_p = ticker_prices.get(f"{clean_sym}BTC", 0.0)
        btc_usdt = ticker_prices.get("BTCUSDT", 0.0)
        if btc_p > 0 and btc_usdt > 0:
            return quantity * btc_p * btc_usdt
        # 4. Par cruzado con ETH
        eth_p = ticker_prices.get(f"{clean_sym}ETH", 0.0)
        eth_usdt = ticker_prices.get("ETHUSDT", 0.0)
        if eth_p > 0 and eth_usdt > 0:
            return quantity * eth_p * eth_usdt
        # 5. Par cruzado con BNB
        bnb_p = ticker_prices.get(f"{clean_sym}BNB", 0.0)
        bnb_usdt = ticker_prices.get("BNBUSDT", 0.0)
        if bnb_p > 0 and bnb_usdt > 0:
            return quantity * bnb_p * bnb_usdt
        return 0.0

    def get_funding_balances(self) -> List[Dict[str, Any]]:
        if not self.is_configured:
            return []
        try:
            headers = {"X-MBX-APIKEY": self.api_key}
            signed_query = self._sign_query({})
            url = f"https://api.binance.com/sapi/v1/asset/get-funding-asset?{signed_query}"
            resp = requests.post(url, headers=headers, timeout=4)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return []

    def get_simple_earn_flexible_positions(self) -> List[Dict[str, Any]]:
        if not self.is_configured:
            return []
        try:
            headers = {"X-MBX-APIKEY": self.api_key}
            signed_query = self._sign_query({})
            url = f"https://api.binance.com/sapi/v1/simple-earn/flexible/position?{signed_query}"
            resp = requests.get(url, headers=headers, timeout=4)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("rows", []) if isinstance(data, dict) else []
        except Exception:
            pass
        return []

    def get_account_balances(self) -> Dict[str, Any]:
        """
        Consulta los saldos REALES de la billetera Spot y fondos de Binance.
        """
        if not self.is_configured:
            return {"authenticated": False, "balances": {}, "usdt_free": 0.0, "error": "Llaves no configuradas"}
        try:
            headers = {"X-MBX-APIKEY": self.api_key}
            signed_query = self._sign_query({})
            url = f"{self.base_url}/account?{signed_query}"
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                balances = {}
                usdt_free = 0.0
                total_stable_free = 0.0
                total_spot_equity = 0.0
                ticker_prices = self.get_all_ticker_prices()

                # 1. Saldos de la Billetera Spot
                for b in data.get("balances", []):
                    free = float(b.get("free", 0.0))
                    locked = float(b.get("locked", 0.0))
                    total = free + locked
                    asset_name = b.get("asset", "").strip()
                    if total > 0 and asset_name:
                        balances[asset_name] = {"free": free, "locked": locked, "total": total}
                        total_spot_equity += self._convert_asset_to_usdt(asset_name, total, ticker_prices)
                    if asset_name in ["USDT", "USDC", "FDUSD", "BUSD"]:
                        total_stable_free += free
                    if asset_name == "USDT":
                        usdt_free = free

                # 2. Saldos de la Billetera de Fondos (Funding Wallet)
                try:
                    funding_items = self.get_funding_balances()
                    for fa in funding_items:
                        f_free = float(fa.get("free", 0.0))
                        f_locked = float(fa.get("locked", 0.0))
                        f_freeze = float(fa.get("freeze", 0.0))
                        f_total = f_free + f_locked + f_freeze
                        f_name = fa.get("asset", "").strip()
                        if f_total > 0 and f_name:
                            total_spot_equity += self._convert_asset_to_usdt(f_name, f_total, ticker_prices)
                except Exception:
                    pass

                # 3. Saldos de Simple Earn Flexible
                try:
                    earn_items = self.get_simple_earn_flexible_positions()
                    for ea in earn_items:
                        e_total = float(ea.get("totalAmount", 0.0))
                        e_name = ea.get("asset", "").strip()
                        if e_total > 0 and e_name:
                            total_spot_equity += self._convert_asset_to_usdt(e_name, e_total, ticker_prices)
                except Exception:
                    pass

                return {
                    "authenticated": True,
                    "can_trade": data.get("canTrade", False),
                    "balances": balances,
                    "usdt_free": usdt_free,
                    "total_stable_free": total_stable_free,
                    "total_spot_equity": round(total_spot_equity, 2),
                    "raw_balances": data.get("balances", [])
                }
            else:
                return {"authenticated": False, "error": f"Error Binance ({resp.status_code}): {resp.text}"}
        except Exception as e:
            return {"authenticated": False, "error": str(e)}

    def create_market_order(self, symbol: str, side: str, quantity: float = 0.0, quote_order_qty: float = 0.0, force_live: bool = False) -> Dict[str, Any]:
        """
        Envía una orden Spot con dinero real a Binance con doble confirmación de seguridad y validación de saldo.
        """
        if not self.is_configured:
            return {"success": False, "error": "Llaves API no configuradas"}
        if force_live:
            self.live_trading_enabled = True
        elif not self.live_trading_enabled:
            return {"success": False, "error": "BLOQUEO DE SEGURIDAD: Modo real no autorizado por el usuario"}

        try:
            headers = {"X-MBX-APIKEY": self.api_key}
            params = {
                "symbol": symbol.upper(),
                "side": side.upper(),
                "type": "MARKET"
            }
            
            # Validación estricta de saldos antes de enviar al exchange para evitar error -2010
            acc = self.get_account_balances()
            if not acc.get("authenticated"):
                return {"success": False, "error": f"No se pudo verificar saldo en Binance: {acc.get('error')}"}

            if side.upper() == "BUY":
                avail_usdt = float(acc.get("usdt_free", 0.0))
                if avail_usdt < 6.0:
                    return {
                        "success": False, 
                        "error": f"Saldo insuficiente en Binance Spot. Saldo disponible: ${avail_usdt:.2f} USDT (Se requiere un mínimo seguro de $6.00 USDT para cumplir el filtro NOTIONAL de Binance y comisiones)."
                    }
                # Asegurar no exceder el saldo disponible
                target_spend = min(quote_order_qty, avail_usdt) if quote_order_qty > 0 else min(10.0, avail_usdt)
                if target_spend > avail_usdt * 0.995:
                    target_spend = round(avail_usdt * 0.99, 2)
                if target_spend < 5.20:
                    return {"success": False, "error": f"Saldo disponible insuficiente (${avail_usdt:.2f} USDT) para cumplir el mínimo seguro de $5.20 USDT."}
                params["quoteOrderQty"] = f"{target_spend:.2f}"
            else:
                import math
                sym_clean = symbol.upper().replace("USDT", "")
                free_qty = float(acc.get("balances", {}).get(sym_clean, {}).get("free", 0.0))
                if free_qty <= 0.0:
                    return {
                        "success": False, 
                        "error": f"Sin saldo disponible en Binance Spot para vender {sym_clean} (Saldo en cartera: 0.0)."
                    }
                
                # Ajustar cantidad exacta al saldo real libre en Binance
                actual_qty = min(quantity, free_qty) if quantity > 0 else free_qty
                
                if sym_clean == "BTC":
                    qty_floored = math.floor(actual_qty * 100000) / 100000
                    params["quantity"] = f"{qty_floored:.5f}"
                elif sym_clean == "ETH":
                    qty_floored = math.floor(actual_qty * 10000) / 10000
                    params["quantity"] = f"{qty_floored:.4f}"
                elif sym_clean in ["BNB", "SOL"]:
                    qty_floored = math.floor(actual_qty * 1000) / 1000
                    params["quantity"] = f"{qty_floored:.3f}"
                elif sym_clean in ["AVAX", "LINK"]:
                    qty_floored = math.floor(actual_qty * 100) / 100
                    params["quantity"] = f"{qty_floored:.2f}"
                elif sym_clean in ["NEAR", "XRP", "ADA"]:
                    qty_floored = math.floor(actual_qty * 10) / 10
                    params["quantity"] = f"{qty_floored:.1f}"
                elif sym_clean == "DOGE":
                    params["quantity"] = f"{int(actual_qty)}"
                else:
                    qty_floored = math.floor(actual_qty * 100) / 100
                    params["quantity"] = f"{qty_floored:.2f}"
                
                if float(params.get("quantity", 0)) <= 0:
                    return {"success": False, "is_dust": True, "error": f"Cantidad de {sym_clean} disponible ({free_qty}) es inferior al mínimo fraccional operable."}

            signed_query = self._sign_query(params)
            url = f"{self.base_url}/order?{signed_query}"
            resp = requests.post(url, headers=headers, timeout=6)
            if resp.status_code in [200, 201]:
                return {"success": True, "data": resp.json()}
            else:
                err_text = resp.text
                is_dust = "-1013" in err_text or "NOTIONAL" in err_text or "Filter failure" in err_text
                return {"success": False, "error": err_text, "is_dust": is_dust}
        except Exception as e:
            return {"success": False, "error": str(e)}


    def test_connection(self) -> Dict[str, Any]:
        """
        Prueba la conexión y reporta el estado exacto del entorno.
        """
        start_t = time.time()
        try:
            ping_resp = requests.get(f"{self.public_url}/ping", timeout=4)
            latency_ms = int((time.time() - start_t) * 1000)
            if ping_resp.status_code != 200:
                return {"connected": False, "error": "No se pudo conectar a Binance"}
        except Exception as e:
            return {"connected": False, "error": f"Error de red Binance: {str(e)}"}

        if not self.is_configured:
            return {
                "connected": True,
                "mode": "PUBLIC_FEED",
                "status": "DATOS EN VIVO ACTIVOS",
                "latency_ms": latency_ms,
                "message": "Leyendo precios oficiales en tiempo real de Binance"
            }

        acc = self.get_account_balances()
        if acc.get("authenticated"):
            return {
                "connected": True,
                "mode": "AUTHENTICATED_ACCOUNT",
                "status": "AUTENTICADO CON BROKER",
                "latency_ms": latency_ms,
                "usdt_balance": acc.get("usdt_free", 0.0),
                "can_trade": acc.get("can_trade", False),
                "live_enabled": self.live_trading_enabled
            }
        else:
            return {
                "connected": True,
                "mode": "PUBLIC_FEED",
                "status": "FEED PÚBLICO ACTIVO",
                "latency_ms": latency_ms,
                "warning": acc.get("error", "Error autenticando llaves")
            }
