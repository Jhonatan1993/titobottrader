import requests
import time
import datetime
from typing import Dict, List, Any, Optional

class AlpacaAdapter:
    def __init__(self, api_key: str = "", secret_key: str = "", base_url: str = "https://paper-api.alpaca.markets"):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")
        self.data_url = "https://data.alpaca.markets/v2"
        self.is_configured = bool(api_key and secret_key)
        self.last_error = ""

    def get_headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Content-Type": "application/json"
        }

    def test_connection(self) -> Dict[str, Any]:
        if not self.api_key or not self.secret_key:
            return {"connected": False, "error": "Llaves API no ingresadas. Agrega tu API Key y Secret Key de Alpaca Paper."}
        try:
            start_t = time.time()
            resp = requests.get(f"{self.base_url}/v2/account", headers=self.get_headers(), timeout=5)
            latency_ms = int((time.time() - start_t) * 1000)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "connected": True,
                    "status": data.get("status", "ACTIVE"),
                    "equity": float(data.get("equity", 0.0)),
                    "cash": float(data.get("cash", 0.0)),
                    "buying_power": float(data.get("buying_power", 0.0)),
                    "currency": data.get("currency", "USD"),
                    "latency_ms": latency_ms
                }
            else:
                err_msg = resp.text
                try:
                    err_msg = resp.json().get("message", resp.text)
                except Exception:
                    pass
                return {"connected": False, "error": f"Error Alpaca ({resp.status_code}): {err_msg}"}
        except Exception as e:
            return {"connected": False, "error": f"Error de red al conectar con Alpaca: {str(e)}"}

    def get_account_summary(self) -> Dict[str, Any]:
        conn = self.test_connection()
        if conn.get("connected"):
            return conn
        return {"connected": False, "equity": 0.0, "cash": 0.0, "status": "DISCONNECTED"}

    def get_latest_stock_prices(self, symbols: List[str]) -> Dict[str, float]:
        if not self.api_key:
            return {}
        try:
            syms_str = ",".join(symbols)
            url = f"{self.data_url}/stocks/bars/latest?symbols={syms_str}&feed=iex"
            resp = requests.get(url, headers=self.get_headers(), timeout=4)
            if resp.status_code == 200:
                data = resp.json().get("bars", {})
                result = {}
                for sym, bar in data.items():
                    if bar and "c" in bar:
                        result[sym] = float(bar["c"])
                return result
        except Exception:
            pass
        return {}

    def submit_order(self, symbol: str, qty: float, side: str = "buy", order_type: str = "market") -> Dict[str, Any]:
        if not self.is_configured:
            return {"success": False, "error": "Alpaca API no configurada"}
        try:
            payload = {
                "symbol": symbol,
                "qty": str(qty) if isinstance(qty, int) else f"{qty:.2f}",
                "side": side.lower(),
                "type": order_type.lower(),
                "time_in_force": "day"
            }
            resp = requests.post(f"{self.base_url}/v2/orders", json=payload, headers=self.get_headers(), timeout=6)
            if resp.status_code in [200, 201]:
                return {"success": True, "order": resp.json()}
            else:
                return {"success": False, "error": resp.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def close_all_positions(self) -> Dict[str, Any]:
        if not self.is_configured:
            return {"success": False, "error": "Alpaca API no configurada"}
        try:
            resp = requests.delete(f"{self.base_url}/v2/positions", headers=self.get_headers(), timeout=6)
            return {"success": resp.status_code in [200, 207]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_positions(self) -> List[Dict[str, Any]]:
        """Obtiene las posiciones abiertas directamente de la cuenta de Alpaca."""
        if not self.is_configured:
            return []
        try:
            resp = requests.get(f"{self.base_url}/v2/positions", headers=self.get_headers(), timeout=5)
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception:
            return []

    def get_stock_bars(self, symbol: str, timeframe: str = "1Min", limit: int = 100) -> List[Dict[str, Any]]:
        """Obtiene velas oficiales de acciones y ETFs de Wall Street desde Alpaca Market Data."""
        if not self.is_configured:
            return []
        try:
            url = f"{self.data_url}/stocks/bars?symbols={symbol.upper()}&timeframe={timeframe}&limit={limit}&feed=iex"
            resp = requests.get(url, headers=self.get_headers(), timeout=5)
            if resp.status_code == 200:
                raw_bars = resp.json().get("bars", {}).get(symbol.upper(), [])
                candles = []
                for b in raw_bars:
                    t_str = b.get("t", "")
                    try:
                        dt = datetime.datetime.fromisoformat(t_str.replace("Z", "+00:00"))
                        unix_ts = int(dt.timestamp())
                    except Exception:
                        unix_ts = int(time.time())
                    candles.append({
                        "time": unix_ts,
                        "open": float(b.get("o", 0.0)),
                        "high": float(b.get("h", 0.0)),
                        "low": float(b.get("l", 0.0)),
                        "close": float(b.get("c", 0.0)),
                        "volume": float(b.get("v", 0.0))
                    })
                return candles
        except Exception:
            pass
        return []

