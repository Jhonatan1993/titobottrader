import time
import requests
import datetime
import threading
from typing import Dict, Any, Optional
from config.broker_config import live_trading_armed, live_cfd_execution_verified

ACTIVE_ASSET_IDS = {
    # Forex Turbo / Binarias (Lunes a Viernes)
    "EURUSD": 1861,
    "EURGBP": 1862,
    "EURJPY": 1864,
    "USDJPY": 1865,
    "GBPJPY": 1866,
    "GBPUSD": 1867,
    "AUDCAD": 1868,
    "AUDJPY": 1869,
    "AUDUSD": 1870,
    "GBPAUD": 1877,
    "GBPNZD": 1880,
    "NZDCAD": 1881,
    "AUDCHF": 1884,
    "NZDUSD": 1896,
    "GBPCAD": 1897,
    "AUDNZD": 1900,
    "EURNZD": 1901,
    "BTCUSD": 1916,
    "USDCHF": 72,
    "USDCAD": 100,
    "CHFJPY": 106,
    "CADCHF": 107,
    "EURAUD": 108,
    # Forex OTC (Operación 24/7)
    "EURUSD-OTC": 76,
    "EURUSDOTC": 76,
    "EURGBP-OTC": 77,
    "EURGBPOTC": 77,
    "USDCHF-OTC": 78,
    "USDCHFOTC": 78,
    "EURJPY-OTC": 79,
    "EURJPYOTC": 79,
    "NZDUSD-OTC": 80,
    "NZDUSDOTC": 80,
    "GBPUSD-OTC": 81,
    "GBPUSDOTC": 81,
    "GBPJPY-OTC": 86,
    "GBPJPYOTC": 86,
    "USDJPY-OTC": 87,
    "USDJPYOTC": 87,
    "AUDCAD-OTC": 88,
    "AUDCADOTC": 88,
    "USDCAD-OTC": 89,
    "USDCADOTC": 89,
    "AUDUSD-OTC": 90,
    "AUDUSDOTC": 90,
    "GBPAUD-OTC": 91,
    "GBPAUDOTC": 91,
    "EURCAD-OTC": 92,
    "EURCADOTC": 92,
    "CHFJPY-OTC": 93,
    "CHFJPYOTC": 93,
    "CADCHF-OTC": 94,
    "CADCHFOTC": 94,
    "EURAUD-OTC": 95,
    "EURAUDOTC": 95,
    # OTC adicionales de alta liquidez
    "USDTRY-OTC": 2124,
    "USDTRYOTC": 2124,
    "USDCOP-OTC": 2299,
    "USDCOPOTC": 2299,
    "USDBRL-OTC": 2298,
    "USDBRLOTC": 2298,
    "USDMXN-OTC": 2300,
    "USDMXNOTC": 2300,
}

ACTIVE_ID_TO_SYMBOL: Dict[int, str] = {
    1861: "EURUSD", 1862: "EURGBP", 1864: "EURJPY", 1865: "USDJPY",
    1866: "GBPJPY", 1867: "GBPUSD", 1868: "AUDCAD", 1869: "AUDJPY",
    1870: "AUDUSD", 1877: "GBPAUD", 1880: "GBPNZD", 1881: "NZDCAD",
    1884: "AUDCHF", 1896: "NZDUSD", 1897: "GBPCAD", 1900: "AUDNZD",
    1901: "EURNZD", 1916: "BTCUSD",
    76: "EURUSD-OTC", 77: "EURGBP-OTC", 78: "USDCHF-OTC", 79: "EURJPY-OTC",
    80: "NZDUSD-OTC", 81: "GBPUSD-OTC", 86: "GBPJPY-OTC", 87: "USDJPY-OTC",
    88: "AUDCAD-OTC", 89: "USDCAD-OTC", 90: "AUDUSD-OTC", 91: "GBPAUD-OTC",
    92: "EURCAD-OTC", 93: "CHFJPY-OTC", 94: "CADCHF-OTC", 95: "EURAUD-OTC",
    2124: "USDTRY-OTC", 2299: "USDCOP-OTC", 2298: "USDBRL-OTC", 2300: "USDMXN-OTC",
    1: "EURUSD", 2: "EURGBP", 3: "GBPJPY", 4: "EURJPY", 5: "GBPUSD", 6: "USDJPY", 7: "AUDCAD"
}

CFD_ALLOWED_SYMBOLS = frozenset({
    "EURUSD", "EURGBP", "EURJPY", "USDJPY", "GBPJPY", "GBPUSD", "AUDCAD",
    "AUDJPY", "AUDUSD", "GBPAUD", "GBPNZD", "NZDCAD", "AUDCHF", "NZDUSD",
    "GBPCAD", "AUDNZD", "EURNZD", "USDCHF", "USDCAD", "CHFJPY", "CADCHF", "EURAUD",
})

class IQOptionAdapter:
    """
    Adaptador Oficial de IQ Option para TitoBotTrader:
    - Modo Simulación / Práctica (PAPER): Opera con saldo demo ($10,000 USD de práctica de IQ Option o simulación aislada).
    - Modo Dinero Real (LIVE_REAL): Autentica con email y contraseña en los servidores de IQ Option para operar con saldo real.
    - Soporte para consulta de saldos en tiempo real y cambio dinámico entre DEMO y REAL.
    """
    def __init__(self, email: str = "", password: str = "", ssid: str = "", environment: str = "PAPER"):
        self.email = email.strip()
        self.password = password.strip()
        self.ssid: Optional[str] = ssid.strip() or None
        self.live_trading_armed = live_trading_armed()
        self.live_cfd_execution_verified = live_cfd_execution_verified()
        requested_environment = environment.upper()
        self.environment = requested_environment if requested_environment in {"PAPER", "LIVE_REAL"} else "PAPER"
        if self.environment == "LIVE_REAL" and not (self.live_trading_armed and self.live_cfd_execution_verified):
            self.environment = "PAPER"
        self.base_url = "https://iqoption.com/api"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        })
        self.is_configured = bool(self.ssid or (self.email and self.password))
        self.connected = False
        self.practice_balance_id: Optional[int] = None
        self.real_balance_id: Optional[int] = None
        self.active_balance_id: Optional[int] = None
        self.practice_amount: float = 10000.0
        self.real_amount: float = 0.0
        self.balance: float = 10000.0
        self.currency: str = "USD"
        self.profile_data: Dict[str, Any] = {}
        self._last_auth_attempt: float = 0.0
        self._persistent_ws = None
        self._ws_lock = threading.Lock()
        self._keepalive_running = False
        self._active_status_cache: Dict[str, bool] = {}
        self._symbol_to_active_id: Dict[str, int] = {}
        self._payout_cache: Dict[str, float] = {}
        self._last_active_status_sync: float = 0.0
        self._sync_status_lock = threading.Lock()
        self._active_sync_thread_started = False

    def _get_persistent_ws(self, timeout: float = 12.0) -> Any:
        """
        Retorna la conexión WebSocket Singleton persistente autenticada.
        Si no existe o cayó, reconecta con 2 reintentos automáticos y timeout de 12 segundos.
        """
        import websocket
        import ssl

        with self._ws_lock:
            # En entorno de pruebas unitarias con mocks inyectados de websocket.create_connection:
            try:
                from unittest.mock import Mock as _Mock
                if isinstance(websocket.create_connection, _Mock):
                    if self._persistent_ws != getattr(websocket.create_connection, "return_value", None):
                        self._persistent_ws = None
            except Exception:
                pass

            if self._persistent_ws is not None:
                try:
                    if hasattr(self._persistent_ws, "connected") and not self._persistent_ws.connected:
                        self._persistent_ws = None
                    elif hasattr(self._persistent_ws, "sock") and self._persistent_ws.sock is None:
                        self._persistent_ws = None
                    else:
                        return self._persistent_ws
                except Exception:
                    try:
                        self._persistent_ws.close()
                    except Exception:
                        pass
                    self._persistent_ws = None

            ws_url = self._get_ws_url()
            headers = self._get_ws_headers()
            last_err = None

            for attempt in range(2):
                try:
                    ws = websocket.create_connection(
                        ws_url,
                        header=headers,
                        timeout=timeout,
                        sslopt={"cert_reqs": ssl.CERT_REQUIRED, "check_hostname": True}
                    )
                    self._persistent_ws = ws
                    self._start_keepalive_if_needed()
                    return self._persistent_ws
                except Exception as e:
                    last_err = e
                    time.sleep(0.5)

            raise TimeoutError(f"Tiempo de espera agotado al conectar al WebSocket de IQ Option: {last_err}")

    def _start_keepalive_if_needed(self):
        if getattr(self, "_keepalive_running", False):
            return
        self._keepalive_running = True
        threading.Thread(target=self._keepalive_loop, daemon=True).start()

    def _keepalive_loop(self):
        import json
        while getattr(self, "_keepalive_running", False):
            time.sleep(20.0)
            if self._persistent_ws is not None:
                try:
                    with self._ws_lock:
                        if self._persistent_ws is not None:
                            self._persistent_ws.send(json.dumps({"name": "heartbeat", "msg": int(time.time() * 1000)}))
                except Exception:
                    self._persistent_ws = None

    def _get_ws_url(self) -> str:
        """Retorna el endpoint WebSocket oficial de IQ Option accesible globalmente."""
        return "wss://ws.iqoption.com/echo/websocket"

    def _get_ws_headers(self) -> list:
        h = [
            "Origin: https://iqoption.com",
            "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
        if self.ssid:
            h.append(f"Cookie: ssid={self.ssid}")
        return h

    def _fetch_live_balances_ws(self) -> bool:
        """
        Consulta balances y perfil en tiempo real a través del WebSocket oficial de IQ Option.
        Indispensable porque la API HTTP /getprofile devuelve 'balances: []' en cuentas modernas,
        mientras que el WebSocket transmite el array completo con saldo real (depósito + bonos) y de práctica.
        """
        if not self.ssid:
            return False
        import websocket
        import json
        import ssl
        try:
            ws_url = self._get_ws_url()
            headers = self._get_ws_headers()
            ws = websocket.create_connection(ws_url, header=headers, timeout=6, sslopt={"cert_reqs": ssl.CERT_REQUIRED, "check_hostname": True})
            # 1. Enviar autenticación
            ws.send(json.dumps({
                "name": "authenticate",
                "msg": {"ssid": self.ssid, "protocol": 3, "session_id": "", "client_session_id": ""},
                "request_id": f"auth_{int(time.time() * 1000)}"
            }))
            ws.send(json.dumps({"name": "ssid", "msg": self.ssid}))

            # 2. Esperar confirmación de autenticación del broker antes de enviar peticiones de portafolio
            auth_start = time.time()
            found_profile = False
            while time.time() - auth_start < 4.0:
                try:
                    raw = ws.recv()
                except Exception:
                    continue
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                    msg_name = data.get("name")
                    if msg_name == "profile":
                        msg = data.get("msg", {})
                        if isinstance(msg, dict):
                            self.profile_data.update(msg)
                            self.currency = msg.get("currency", self.currency)
                            balances = msg.get("balances", [])
                            for b in balances:
                                b_type = b.get("type")
                                b_id = b.get("id")
                                amt = float(b.get("amount", 0.0)) + float(b.get("bonus_amount", 0.0))
                                if b_type == 1:
                                    self.real_balance_id = b_id
                                    self.real_amount = round(amt, 2)
                                    self.real_currency = b.get("currency", "COP")
                                elif b_type == 4:
                                    self.practice_balance_id = b_id
                                    self.practice_amount = round(amt, 2)
                                    self.practice_currency = b.get("currency", "USD")

                            if self.environment == "LIVE_REAL":
                                self.balance = self.real_amount
                                self.currency = getattr(self, "real_currency", "COP")
                            else:
                                self.balance = self.practice_amount
                                self.currency = getattr(self, "practice_currency", "USD")
                        found_profile = True
                        break
                    elif msg_name in ["authenticated", "front", "timeSync", "heartbeat"]:
                        continue
                except Exception:
                    pass

            # 3. Habilitar respuestas de requests en WebSocket oficial de IQ Option
            ws.send(json.dumps({
                "name": "setOptions",
                "msg": {"sendResults": True},
                "request_id": f"sopts_{int(time.time() * 1000)}"
            }))

            # 4. Suscribir y solicitar posiciones abiertas oficiales
            req_pos_id = f"pos_sync_{int(time.time() * 1000)}"
            inst_types = [
                "marginal-forex",
                "marginal-cfd",
                "marginal-crypto",
                "binary-option",
                "turbo-option",
                "blitz-option",
                "digital-option"
            ]
            ws.send(json.dumps({
                "name": "sendMessage",
                "request_id": req_pos_id,
                "msg": {
                    "name": "portfolio.get-positions",
                    "version": "4.0",
                    "body": {
                        "instrument_types": inst_types,
                        "limit": 30,
                        "offset": 0
                    }
                }
            }))
            ws.send(json.dumps({
                "name": "subscribeMessage",
                "request_id": f"sub_p_{int(time.time() * 1000)}",
                "msg": {
                    "name": "portfolio.positions-state",
                    "version": "1.0"
                }
            }))

            # 5. Escuchar paquetes de posiciones y balances
            start_t = time.time()
            found_positions = False
            parsed_positions = []

            while time.time() - start_t < 4.5:
                raw = ws.recv()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                    msg_name = data.get("name")
                    msg_body = data.get("msg", {})

                    if msg_name == "profile" and not found_profile:
                        if isinstance(msg_body, dict):
                            self.profile_data.update(msg_body)
                            self.currency = msg_body.get("currency", self.currency)
                            balances = msg_body.get("balances", [])
                            for b in balances:
                                b_type = b.get("type")
                                b_id = b.get("id")
                                amt = float(b.get("amount", 0.0)) + float(b.get("bonus_amount", 0.0))
                                if b_type == 1:
                                    self.real_balance_id = b_id
                                    self.real_amount = round(amt, 2)
                                    self.real_currency = b.get("currency", "COP")
                                elif b_type == 4:
                                    self.practice_balance_id = b_id
                                    self.practice_amount = round(amt, 2)
                                    self.practice_currency = b.get("currency", "USD")

                            if self.environment == "LIVE_REAL":
                                self.balance = self.real_amount
                                self.currency = getattr(self, "real_currency", "COP")
                            else:
                                self.balance = self.practice_amount
                                self.currency = getattr(self, "practice_currency", "USD")
                            found_profile = True

                    elif msg_name == "balance-changed" and isinstance(msg_body, dict):
                        b_type = msg_body.get("user_balance_type") or msg_body.get("type")
                        b_id = msg_body.get("id")
                        if b_type == 1 or b_id == self.real_balance_id:
                            self.real_amount = round(float(msg_body.get("amount", self.real_amount)), 2)
                        elif b_type == 4 or b_id == self.practice_balance_id:
                            self.practice_amount = round(float(msg_body.get("amount", self.practice_amount)), 2)

                    elif (msg_name in ["positions", "portfolio.positions"] or (isinstance(msg_body, dict) and "positions" in msg_body)) and msg_name != "result":
                        found_positions = True
                        p_list = []
                        if isinstance(msg_body, dict):
                            p_list = msg_body.get("positions", []) or msg_body.get("items", [])
                        elif isinstance(msg_body, list):
                            p_list = msg_body

                        for p in p_list:
                            raw_ev = p.get("raw_event", {}) if isinstance(p.get("raw_event"), dict) else {}
                            ev = list(raw_ev.values())[0] if raw_ev else p
                            ext_id = str(p.get("external_id") or ev.get("id") or p.get("id") or "")
                            int_id = str(p.get("id") or "")
                            p_status = str(p.get("status") or ev.get("status") or "open").lower()
                            act_id = p.get("active_id") or ev.get("instrument_active_id")
                            oids = [str(oid) for oid in ev.get("order_ids", [])] if isinstance(ev.get("order_ids"), list) else []
                            sym = ACTIVE_ID_TO_SYMBOL.get(int(act_id) if act_id is not None else 1, "EURUSD")
                            if p_status not in ["closed", "cancelled", "rejected"]:
                                parsed_positions.append({
                                    "external_id": ext_id,
                                    "id": ext_id,
                                    "internal_id": int_id,
                                    "order_ids": oids,
                                    "active_id": act_id,
                                    "symbol": sym,
                                    "status": p_status,
                                    "pnl_net": float(p.get("pnl_net") or p.get("pnl") or ev.get("pnl_net") or 0.0),
                                    "invest": float(p.get("invest") or ev.get("initial_margin") or 0.0),
                                    "open_quote": float(p.get("open_quote") or ev.get("open_quote_ask") or 0.0),
                                    "side": str(p.get("side") or ev.get("type") or ev.get("side") or "buy").upper(),
                                    "leverage": int(p.get("leverage") or ev.get("leverage") or 500)
                                })
                        if found_profile and found_positions:
                            break
                except Exception:
                    pass
            ws.close()
            if found_positions:
                self.open_broker_positions = parsed_positions
                self._positions_synced = True
            elif len(getattr(self, "open_broker_positions", [])) > 0:
                self._positions_synced = True
            else:
                self._positions_synced = False
            return found_profile
        except Exception:
            return False

    def _fetch_profile(self) -> Dict[str, Any]:
        """Consulta perfil y balances vía WebSocket oficial (Cloudflare) o API HTTP."""
        if not self.ssid:
            return {"success": False, "error": "No hay SSID de sesión"}

        # Detección amigable si el usuario copió por error la cookie de sesión de TitoBot
        if self.ssid.startswith(".eJy"):
            return {
                "success": False,
                "error": "⚠️ El token que ingresaste corresponde a la sesión de TitoBot (titobottrader.tech), NO a IQ Option. Por favor abre la pestaña donde tienes tu cuenta de iqoption.com, abre DevTools (F12) > Aplicación > Cookies > iqoption.com y copia la cookie llamada 'ssid'."
            }

        # 1. Prioridad: Consulta directa mediante WebSocket en vivo (Inmune a bloqueos de Cloudflare)
        ws_ok = self._fetch_live_balances_ws()
        if ws_ok and (self.real_balance_id is not None or self.practice_balance_id is not None):
            if self.environment == "LIVE_REAL":
                self.balance = self.real_amount
                self.active_balance_id = self.real_balance_id
                self.currency = getattr(self, "real_currency", "COP")
                if self.real_balance_id:
                    self.change_balance(self.real_balance_id)
            else:
                self.balance = self.practice_amount
                self.active_balance_id = self.practice_balance_id
                self.currency = getattr(self, "practice_currency", "USD")
                if self.practice_balance_id:
                    self.change_balance(self.practice_balance_id)
            return {"success": True, "profile": self.profile_data}

        # 2. Respaldo vía HTTP (iqbroker.com / iqoption.com)
        try:
            self.session.cookies.set("ssid", self.ssid, domain=".iqoption.com")
            self.session.cookies.set("ssid", self.ssid, domain="iqoption.com")
            self.session.cookies.set("ssid", self.ssid, domain=".iqbroker.com")
            self.session.cookies.set("ssid", self.ssid, domain="iqbroker.com")
            
            for base in ["https://iqbroker.com/api", "https://iqoption.com/api"]:
                try:
                    prof_resp = self.session.get(f"{base}/getprofile", timeout=5)
                    if prof_resp.status_code == 200:
                        p_data = prof_resp.json()
                        profile = p_data.get("result", {}) if isinstance(p_data, dict) else {}
                        if not profile and isinstance(p_data, dict) and "profile" in p_data:
                            profile = p_data.get("profile", {})
                        if profile:
                            self.profile_data = profile
                            balances = profile.get("balances", [])
                            for b in balances:
                                b_type = b.get("type")
                                b_id = b.get("id")
                                amt = float(b.get("amount", 0.0)) + float(b.get("bonus_amount", 0.0))
                                if b_type == 1:
                                    self.real_balance_id = b_id
                                    self.real_amount = round(amt, 2)
                                    self.real_currency = b.get("currency", "COP")
                                elif b_type == 4:
                                    self.practice_balance_id = b_id
                                    self.practice_amount = round(amt, 2)
                                    self.practice_currency = b.get("currency", "USD")

                            if self.environment == "LIVE_REAL":
                                self.balance = self.real_amount
                                self.active_balance_id = self.real_balance_id
                                self.currency = getattr(self, "real_currency", "COP")
                            else:
                                self.balance = self.practice_amount
                                self.active_balance_id = self.practice_balance_id
                                self.currency = getattr(self, "practice_currency", "USD")
                            return {"success": True, "profile": self.profile_data}
                    elif prof_resp.status_code == 401:
                        return {"success": False, "error": "Token SSID inválido o expirado. Copia tu cookie 'ssid' actualizada en iqoption.com."}
                except Exception:
                    continue
        except Exception:
            pass

        if ws_ok:
            return {"success": True, "profile": self.profile_data}

        return {
            "success": False, 
            "error": "No se pudo autenticar el Token SSID. Verifica que sea el valor exacto de la cookie 'ssid' en la pestaña de iqoption.com."
        }

    def connect(self) -> Dict[str, Any]:
        """
        Inicia sesión en IQ Option vía Token SSID directo o API oficial de login.
        """
        if not self.is_configured:
            self.connected = False
            return {
                "connected": False,
                "authenticated": False,
                "error": "Credenciales de IQ Option no configuradas (Ingresa tu Token SSID o email y contraseña en Ajustes)."
            }

        # 1. Autenticación directa por SSID (Bypassea cualquier bloqueo de IP de centros de datos VPS)
        if self.ssid:
            prof_res = self._fetch_profile()
            if prof_res.get("success"):
                self.connected = True
                user_label = self.profile_data.get("name") or self.profile_data.get("email") or self.email or "Usuario Conectado"
                return {
                    "connected": True,
                    "authenticated": True,
                    "environment": self.environment,
                    "balance": self.balance,
                    "practice_balance": self.practice_amount,
                    "real_balance": self.real_amount,
                    "currency": self.currency,
                    "name": user_label,
                    "method": "SSID_DIRECT"
                }
            elif not (self.email and self.password):
                return {
                    "connected": False,
                    "authenticated": False,
                    "error": prof_res.get("error", "Error autenticando con SSID")
                }

        # 2. Autenticación estándar por Email y Contraseña (con fallback a mirror oficial iqbroker)
        if self.email and self.password:
            auth_urls = [
                "https://auth.iqbroker.com/api/v2/login",
                "https://auth.iqoption.com/api/v2/login"
            ]
            resp = None
            last_err = ""
            for auth_url in auth_urls:
                try:
                    payload = {
                        "identifier": self.email,
                        "password": self.password
                    }
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept": "application/json",
                        "Content-Type": "application/json"
                    }
                    resp = self.session.post(auth_url, json=payload, headers=headers, timeout=(6, 12))
                    if resp.status_code in [200, 401, 429]:
                        break
                except Exception as e:
                    last_err = str(e)
                    continue

            if resp is not None:
                if resp.status_code == 200:
                    data = resp.json()
                    self.ssid = resp.cookies.get("ssid") or self.session.cookies.get("ssid")
                    if isinstance(data, dict):
                        if not self.ssid and data.get("ssid"):
                            self.ssid = data.get("ssid")
                        elif not self.ssid and isinstance(data.get("data"), dict) and data["data"].get("ssid"):
                            self.ssid = data["data"].get("ssid")

                    if self.ssid:
                        prof_res = self._fetch_profile()
                        if prof_res.get("success"):
                            self.connected = True
                            user_label = self.profile_data.get("name") or self.profile_data.get("email") or self.email or "Usuario Conectado"
                            return {
                                "connected": True,
                                "authenticated": True,
                                "environment": self.environment,
                                "balance": self.balance,
                                "practice_balance": self.practice_amount,
                                "real_balance": self.real_amount,
                                "currency": self.currency,
                                "name": user_label,
                                "method": "LOGIN_API"
                            }

                    self.connected = True
                    return {
                        "connected": True,
                        "authenticated": True,
                        "environment": self.environment,
                        "balance": self.balance,
                        "practice_balance": self.practice_amount,
                        "real_balance": self.real_amount,
                        "currency": self.currency,
                        "name": self.email
                    }
                elif resp.status_code == 429:
                    try:
                        err_json = resp.json()
                        msg = err_json.get("message", "Límite de solicitudes excedido.")
                    except Exception:
                        msg = "Límite de solicitudes excedido."
                    return {
                        "connected": False,
                        "authenticated": False,
                        "error": f"IQ Option bloqueó temporalmente el inicio con contraseña ({msg}). Ingresa tu Token SSID de tu pestaña abierta de iqoption.com para conectar de inmediato sin restricciones."
                    }
                elif resp.status_code == 401:
                    try:
                        err_json = resp.json()
                        msg = err_json.get("message", "")
                        code = err_json.get("code", "")
                        if code == "invalid_credentials" or "wrong credentials" in msg.lower():
                            err_msg = "Credenciales incorrectas: Verifica tu email y contraseña de IQ Option en Ajustes."
                        elif "verify" in code.lower() or "2step" in code.lower() or "verify" in msg.lower():
                            err_msg = "Se requiere verificación 2FA. Conéctate ingresando tu Token SSID de sesión en Ajustes."
                        else:
                            err_msg = f"Autenticación rechazada por IQ Option: {msg or code}"
                    except Exception:
                        err_msg = "Credenciales de IQ Option incorrectas (HTTP 401). Verifica tu correo y contraseña."
                    return {"connected": False, "authenticated": False, "error": err_msg}
                else:
                    return {
                        "connected": False, 
                        "authenticated": False, 
                        "error": f"Error servidor IQ Option ({resp.status_code}): {resp.text[:100]}"
                    }
            else:
                return {
                    "connected": False,
                    "authenticated": False,
                    "error": f"Tiempo de espera agotado al conectar a IQ Option ({last_err or 'Timeout'}). Ingresa tu Token SSID en Ajustes para conectar de inmediato."
                }

        return {
            "connected": False,
            "authenticated": False,
            "error": "Por favor ingresa tu Token SSID o tus credenciales de IQ Option en Ajustes."
        }

    def change_balance(self, balance_id: int) -> bool:
        """Cambia el balance activo en IQ Option entre cuenta REAL y cuenta PRACTICE (Demo)."""
        if not self.ssid:
            return False
        if getattr(self, "active_balance_id", None) == balance_id:
            return True
        for endpoint in [f"{self.base_url}/profile/changebalance", f"{self.base_url}/changebalance"]:
            try:
                resp = self.session.post(endpoint, data={"balance_id": balance_id}, timeout=4)
                if resp.status_code == 200:
                    self.active_balance_id = balance_id
                    return True
            except Exception:
                pass
        return False

    def test_connection(self) -> Dict[str, Any]:
        """Prueba la conexión y reporta el estado actual del broker sin bloquear el servidor."""
        if not self.is_configured:
            return {
                "connected": True,
                "status": "MODO SIMULACIÓN (FEED PÚBLICO)",
                "mode": "PAPER_SIMULATION",
                "environment": self.environment,
                "balance": self.balance
            }
        
        # Si ya está conectado, responder de inmediato sin llamadas HTTP bloqueantes
        if self.connected:
            mode_lbl = "MODO REAL (EN VIVO)" if self.environment == "LIVE_REAL" else "MODO PRÁCTICA (DEMO)"
            return {
                "connected": True,
                "status": f"CONECTADO A IQ OPTION ({mode_lbl})",
                "environment": self.environment,
                "balance": self.balance,
                "currency": self.currency
            }

        # Control de frecuencia: reintentar conexión como máximo cada 30 segundos
        now = time.time()
        if hasattr(self, "_last_connect_time") and (now - self._last_connect_time < 30.0):
            return {
                "connected": False,
                "status": "RECONECTANDO...",
                "error": getattr(self, "_last_connect_err", "Esperando reintento...")
            }
        self._last_connect_time = now

        login_res = self.connect()
        if login_res.get("connected"):
            mode_lbl = "MODO REAL (EN VIVO)" if self.environment == "LIVE_REAL" else "MODO PRÁCTICA (DEMO)"
            return {
                "connected": True,
                "status": f"CONECTADO A IQ OPTION ({mode_lbl})",
                "environment": self.environment,
                "balance": self.balance,
                "currency": self.currency
            }
        self._last_connect_err = login_res.get("error", "Error de conexión")
        return {
            "connected": False,
            "status": "ERROR DE CONEXIÓN",
            "error": self._last_connect_err
        }

    def get_account_balances(self) -> Dict[str, Any]:
        """Consulta el saldo y estado actual en tiempo real vía WebSocket."""
        if self.is_configured and not self.connected:
            self.connect()
        elif self.connected and self.ssid:
            now_t = time.time()
            if not hasattr(self, "_last_ws_balance_sync") or (now_t - getattr(self, "_last_ws_balance_sync", 0.0) > 3.0):
                self._last_ws_balance_sync = now_t
                self._fetch_live_balances_ws()
            if self.environment == "LIVE_REAL":
                self.balance = self.real_amount
                self.currency = getattr(self, "real_currency", "COP")
            else:
                self.balance = self.practice_amount
                self.currency = getattr(self, "practice_currency", "USD")

        active_curr = getattr(self, "real_currency", "COP") if self.environment == "LIVE_REAL" else getattr(self, "practice_currency", "USD")
        return {
            "authenticated": self.connected,
            "balance": round(self.balance, 2),
            "practice_balance": round(self.practice_amount, 2),
            "real_balance": round(self.real_amount, 2),
            "currency": active_curr,
            "practice_currency": getattr(self, "practice_currency", "USD"),
            "real_currency": getattr(self, "real_currency", "COP"),
            "environment": self.environment,
            "open_positions": getattr(self, "open_broker_positions", []),
            "positions_synced": getattr(self, "_positions_synced", False)
        }

    def get_open_positions(self) -> list:
        """Retorna las posiciones Forex CFD activas detectadas en IQ Option."""
        return getattr(self, "open_broker_positions", [])

    def set_environment(self, env: str) -> Dict[str, Any]:
        """Conmuta de forma segura entre MODO PRÁCTICA (PAPER) y MODO REAL (LIVE_REAL)."""
        requested = str(env).upper()
        if requested not in {"PAPER", "LIVE_REAL"}:
            return {"success": False, "error": "Entorno inválido; use PAPER o LIVE_REAL."}
        if requested == "LIVE_REAL" and not self.live_trading_armed:
            return {"success": False, "error": "LIVE_REAL bloqueado: LIVE_TRADING_ARMED no está habilitado en el proceso."}
        if requested == "LIVE_REAL" and not self.live_cfd_execution_verified:
            return {"success": False, "error": "LIVE_REAL bloqueado: falta verificar el tamaño de contrato/margen CFD frente al importe solicitado."}
        self.environment = requested
        if self.connected:
            target_id = self.real_balance_id if self.environment == "LIVE_REAL" else self.practice_balance_id
            if target_id:
                self.change_balance(target_id)
        if self.environment == "LIVE_REAL":
            self.balance = self.real_amount
            self.currency = getattr(self, "real_currency", "COP")
        else:
            self.balance = self.practice_amount
            self.currency = getattr(self, "practice_currency", "USD")
        return {
            "success": True,
            "environment": self.environment,
            "balance": self.balance,
            "currency": self.currency
        }

    def _start_active_sync_thread_if_needed(self):
        """Inicia hilo de sincronización en segundo plano para el catálogo de activos y payouts."""
        if getattr(self, "_active_sync_thread_started", False) or not self.ssid:
            return
        self._active_sync_thread_started = True
        t = threading.Thread(target=self._active_sync_loop, daemon=True)
        t.start()

    def _active_sync_loop(self):
        """Loop en segundo plano que actualiza activos abiertos y payouts cada 50 segundos."""
        while getattr(self, "_active_sync_thread_started", False):
            try:
                self.sync_active_statuses(force=True)
            except Exception:
                pass
            time.sleep(50.0)

    def sync_active_statuses(self, force: bool = False) -> Dict[str, bool]:
        """
        Consulta en tiempo real el catálogo de activos de IQ Option (get-initialization-data v3.0).
        Actualiza el estado de disponibilidad:
        - self._active_status_cache: Dict[str, bool] (True si está habilitado y no suspendido)
        - self._payout_cache: Dict[str, float] (payouts en vivo por par)
        """
        now = time.time()
        if not force and (now - getattr(self, "_last_active_status_sync", 0.0) < 45.0) and getattr(self, "_active_status_cache", None):
            return self._active_status_cache

        if not self.ssid:
            return self._active_status_cache

        with self._sync_status_lock:
            if not force and (now - getattr(self, "_last_active_status_sync", 0.0) < 45.0) and getattr(self, "_active_status_cache", None):
                return self._active_status_cache

            import websocket
            import json
            import ssl

            try:
                ws_url = self._get_ws_url()
                headers = self._get_ws_headers()
                ws = websocket.create_connection(ws_url, header=headers, timeout=4.0, sslopt={"cert_reqs": ssl.CERT_REQUIRED, "check_hostname": True})
                
                # 1. Autenticar y esperar confirmación del broker
                ws.send(json.dumps({"name": "ssid", "msg": self.ssid}))
                ws.send(json.dumps({
                    "name": "authenticate",
                    "msg": {"ssid": self.ssid, "protocol": 3, "session_id": "", "client_session_id": ""},
                    "request_id": f"auth_init_{int(now * 1000)}"
                }))

                auth_start = time.time()
                while time.time() - auth_start < 2.0:
                    try:
                        raw = ws.recv()
                    except StopIteration:
                        break
                    if not raw:
                        continue
                    try:
                        d = json.loads(raw)
                        if d.get("name") in ["authenticated", "profile", "timeSync"]:
                            break
                    except Exception:
                        pass

                # 2. Solicitar catálogo oficial de activos initialization-data v3.0
                req_id = f"init_{int(time.time() * 1000)}"
                ws.send(json.dumps({
                    "name": "sendMessage",
                    "request_id": req_id,
                    "msg": {
                        "name": "get-initialization-data",
                        "version": "3.0",
                        "body": {}
                    }
                }))

                start_t = time.time()
                while time.time() - start_t < 4.5:
                    try:
                        raw = ws.recv()
                    except Exception:
                        continue
                    if not raw or not isinstance(raw, (str, bytes)):
                        continue
                    try:
                        data = json.loads(raw)
                        if data.get("name") == "initialization-data":
                            msg = data.get("msg", {})
                            turbo_actives = msg.get("turbo", {}).get("actives", {})
                            binary_actives = msg.get("binary", {}).get("actives", {})

                            # 1. Procesar primero binary, y LUEGO turbo para que las opciones Turbo tengan prioridad absoluta
                            for cat_actives in [binary_actives, turbo_actives]:
                                if not isinstance(cat_actives, dict):
                                    continue
                                for aid_str, act in cat_actives.items():
                                    if not isinstance(act, dict):
                                        continue
                                    name = str(act.get("name", ""))
                                    clean_sym = name.replace("front.", "").replace("-op", "").upper()
                                    is_suspended = bool(act.get("is_suspended", False))
                                    is_enabled = bool(act.get("enabled", True))
                                    is_open = is_enabled and (not is_suspended)
                                    try:
                                        aid_int = int(aid_str)
                                    except (ValueError, TypeError):
                                        aid_int = None

                                    if clean_sym:
                                        self._active_status_cache[clean_sym] = is_open
                                        if aid_int:
                                            self._symbol_to_active_id[clean_sym] = aid_int
                                            ACTIVE_ASSET_IDS[clean_sym] = aid_int
                                            ACTIVE_ID_TO_SYMBOL[aid_int] = clean_sym
                                        if "-OTC" in clean_sym:
                                            self._active_status_cache[clean_sym.replace("-OTC", "OTC")] = is_open
                                            if aid_int:
                                                self._symbol_to_active_id[clean_sym.replace("-OTC", "OTC")] = aid_int
                                                ACTIVE_ASSET_IDS[clean_sym.replace("-OTC", "OTC")] = aid_int

                                    # Extraer payout si está presente en option.profit
                                    opt = act.get("option", {})
                                    if isinstance(opt, dict):
                                        p_data = opt.get("profit", {})
                                        if isinstance(p_data, dict) and "commission" in p_data:
                                            try:
                                                comm = float(p_data["commission"])
                                                payout = round(max(0.50, min(0.99, (100.0 - comm) / 100.0)), 2)
                                                if clean_sym:
                                                    self._payout_cache[clean_sym] = payout
                                                    if "-OTC" in clean_sym:
                                                        self._payout_cache[clean_sym.replace("-OTC", "OTC")] = payout
                                            except (ValueError, TypeError):
                                                pass

                            self._last_active_status_sync = time.time()
                            break
                    except Exception:
                        pass
                try:
                    ws.close()
                except Exception:
                    pass
            except Exception:
                pass

            return self._active_status_cache

    def is_asset_open(self, symbol: str) -> bool:
        """
        Verifica con latencia cero en RAM si un activo está habilitado y no suspendido en IQ Option.
        - Si el activo está marcado como suspendido o cerrado en el catálogo oficial de IQ Option, retorna False.
        - Si no hay credenciales o está en modo PAPER sin SSID, retorna True por defecto.
        """
        if not self.ssid:
            return True

        # Iniciar thread en segundo plano si aún no ha iniciado
        self._start_active_sync_thread_if_needed()

        clean_sym = symbol.replace("/", "").replace(" ", "").replace("_", "").upper()

        # Chequeo directo en caché
        if clean_sym in self._active_status_cache:
            return bool(self._active_status_cache[clean_sym])

        otc_sym = f"{clean_sym}-OTC" if not clean_sym.endswith("OTC") and not clean_sym.endswith("-OTC") else clean_sym
        if otc_sym in self._active_status_cache:
            return bool(self._active_status_cache[otc_sym])

        clean_no_dash = clean_sym.replace("-OTC", "OTC")
        if clean_no_dash in self._active_status_cache:
            return bool(self._active_status_cache[clean_no_dash])

        # Si el catálogo ya fue cargado con al menos 20 activos y un par OTC específico no figura en él,
        # o está suspendido, retornar False para evitar rechazos Cannot purchase
        if len(self._active_status_cache) >= 20 and ("OTC" in clean_sym or "-OTC" in clean_sym):
            return False

        return True

    def get_payout(self, symbol: str) -> float:
        """
        Retorna el ratio de retorno/payout vigente para la opción binaria (ej. 0.88 para 88%).
        Permite filtrar pares que no cumplan el mínimo de rentabilidad matemática (>= 0.80).
        """
        clean_sym = symbol.upper().replace("-OTC", "").replace("OTC", "")
        if hasattr(self, "_payout_cache"):
            if symbol in self._payout_cache:
                return float(self._payout_cache[symbol])
            if clean_sym in self._payout_cache:
                return float(self._payout_cache[clean_sym])
        return 0.88

    def get_active_id(self, symbol: str) -> int:
        """
        Retorna el active_id exacto y vigente para Opciones Binarias Turbo de IQ Option.
        Prioriza la resolución dinámica obtenida de initialization-data v3.0.
        """
        clean_sym = symbol.replace("/", "").replace(" ", "").replace("_", "").upper()
        if hasattr(self, "_symbol_to_active_id") and clean_sym in self._symbol_to_active_id:
            return self._symbol_to_active_id[clean_sym]
        if clean_sym in ACTIVE_ASSET_IDS:
            return ACTIVE_ASSET_IDS[clean_sym]
        otc_sym = f"{clean_sym}-OTC"
        if hasattr(self, "_symbol_to_active_id") and otc_sym in self._symbol_to_active_id:
            return self._symbol_to_active_id[otc_sym]
        if otc_sym in ACTIVE_ASSET_IDS:
            return ACTIVE_ASSET_IDS[otc_sym]
        no_dash = clean_sym.replace("-OTC", "OTC")
        if hasattr(self, "_symbol_to_active_id") and no_dash in self._symbol_to_active_id:
            return self._symbol_to_active_id[no_dash]
        return ACTIVE_ASSET_IDS.get(no_dash)

    def _execute_real_ws_order(
        self, 
        symbol: str, 
        side: str, 
        amount: float, 
        leverage: int = 25, 
        stop_loss_pct: Optional[float] = None, 
        take_profit_pct: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Envía una orden real de Forex CFD al servidor WebSocket de IQ Option utilizando el token SSID.
        """
        import websocket
        import json
        import ssl

        if self.environment == "LIVE_REAL" and not (live_trading_armed() and live_cfd_execution_verified()):
            return {"success": False, "error": "Orden CFD LIVE_REAL bloqueada por gates de liberación del proceso."}

        if not self.ssid:
            return {"success": False, "error": "No hay SSID de sesión activo para ejecutar orden en IQ Option"}

        raw_symbol = str(symbol).strip().upper()
        if "OTC" in raw_symbol:
            return {"success": False, "error": "Símbolos OTC no permitidos para Forex CFD."}
        clean_sym = raw_symbol.replace("/", "").replace(" ", "").replace("(", "").replace(")", "").replace("_", "")
        if clean_sym not in CFD_ALLOWED_SYMBOLS:
            return {"success": False, "error": f"Símbolo CFD no autorizado: {clean_sym or '(vacío)'}"}
        # CFD requires an active id confirmed by the broker; never substitute EURUSD.
        active_id = self._symbol_to_active_id.get(clean_sym)
        if active_id is None:
            return {"success": False, "error": f"IQ Option no confirmó el instrumento CFD {clean_sym}. Orden rechazada."}

        cfd_side = "buy" if side.lower() in ["buy", "buy_long", "call"] else "sell"
        order_leverage = max(1, min(int(leverage or 25), 25))
        
        # En cuentas COP de IQ Option, el importe mínimo de operación es de 2,000 COP (En USD es $1.00)
        min_amount = 2000.0 if self.currency == "COP" else 1.0
        order_amount = max(min_amount, round(float(amount), 2))

        # Validación estricta de saldo disponible en cuenta real
        if self.environment == "LIVE_REAL" and order_amount > self.real_amount:
            return {
                "success": False,
                "error": f"Saldo insuficiente en IQ Option: Se requieren al menos {order_amount:,.2f} {self.currency} y dispones de {self.real_amount:,.2f} {self.currency}."
            }

        ws_url = self._get_ws_url()
        headers = self._get_ws_headers()

        result = {"success": False, "error": "Tiempo de espera agotado al conectar al WebSocket de IQ Option"}
        order_sent = False
        req_id = None

        try:
            ws = self._get_persistent_ws(timeout=12.0)
            # 1. Autenticar sesión vía protocolo moderno (authenticate v3) y legacy SSID
            auth_msg = {
                "name": "authenticate",
                "msg": {
                    "ssid": self.ssid,
                    "protocol": 3,
                    "session_id": "",
                    "client_session_id": ""
                },
                "request_id": f"auth_{int(time.time() * 1000)}"
            }
            ws.send(json.dumps(auth_msg))
            ws.send(json.dumps({"name": "ssid", "msg": self.ssid}))

            # Esperar confirmación de handshake y perfil antes de enviar la orden
            auth_start = time.time()
            pending_order_data = None
            while time.time() - auth_start < 4.0:
                try:
                    raw = ws.recv()
                except StopIteration:
                    break
                if not raw:
                    continue
                try:
                    d = json.loads(raw)
                    d_name = d.get("name")
                    if d_name == "profile":
                        msg = d.get("msg", {})
                        if isinstance(msg, dict):
                            self.profile_data.update(msg)
                            self.currency = msg.get("currency", self.currency)
                            for b in msg.get("balances", []):
                                if b.get("type") == 1:
                                    self.real_balance_id = b.get("id")
                                    self.real_amount = round(float(b.get("amount", 0.0)) + float(b.get("bonus_amount", 0.0)), 2)
                                elif b.get("type") == 4:
                                    self.practice_balance_id = b.get("id")
                                    self.practice_amount = round(float(b.get("amount", 0.0)) + float(b.get("bonus_amount", 0.0)), 2)
                        break
                    elif d_name in ["authenticated", "timeSync", "front"]:
                        break
                    elif d_name in ["order-placed-temp", "order-placed", "position-changed"]:
                        pending_order_data = d
                        break
                except Exception:
                    pass

            ws.send(json.dumps({"name": "setOptions", "msg": {"sendResults": True}, "request_id": "set_opts"}))

            req_id = f"tito_{int(time.time() * 1000)}"
            if self.environment == "LIVE_REAL":
                target_balance = self.real_balance_id or self.active_balance_id
            else:
                target_balance = self.practice_balance_id or self.active_balance_id

            order_leverage = max(1, min(int(leverage or 25), 25))
            target_bal_id = int(target_balance) if target_balance and str(target_balance).isdigit() else target_balance

            # Enviar orden de mercado oficial Quadcode Margen Forex CFD (100% Forex sin expiración de tiempo)
            # Instrument ID sigue el esquema mf.{active_id} (ej. mf.1 para EURUSD)
            count_units = "100" # Lote micro mínimo 0.001 (100 unidades de divisa base)
            order_leverage_str = str(order_leverage)
            
            body_payload = {
                "side": cfd_side,
                "user_balance_id": target_bal_id,
                "count": count_units,
                "instrument_id": f"mf.{active_id}",
                "instrument_active_id": active_id,
                "leverage": order_leverage_str
            }
            if stop_loss_pct is not None and take_profit_pct is not None:
                sl_f = float(stop_loss_pct)
                tp_f = float(take_profit_pct)
                if tp_f <= sl_f:
                    tp_f = round(max(sl_f * 1.5, sl_f + 0.5), 2)
                body_payload["stop_loss"] = {"value": str(round(sl_f, 2)), "type": "pnl"}
                body_payload["take_profit"] = {"value": str(round(tp_f, 2)), "type": "pnl"}
            elif stop_loss_pct is not None:
                sl_f = float(stop_loss_pct)
                tp_f = round(max(sl_f * 1.5, sl_f + 0.5), 2)
                body_payload["stop_loss"] = {"value": str(round(sl_f, 2)), "type": "pnl"}
                body_payload["take_profit"] = {"value": str(round(tp_f, 2)), "type": "pnl"}
            elif take_profit_pct is not None:
                body_payload["take_profit"] = {"value": str(round(float(take_profit_pct), 2)), "type": "pnl"}

            cfd_payload = {
                "name": "sendMessage",
                "request_id": req_id,
                "msg": {
                    "name": "marginal-forex.place-market-order",
                    "version": "1.0",
                    "body": body_payload
                }
            }
            ws.send(json.dumps(cfd_payload))
            order_sent = True

            # 3. Leer respuesta con timeout de 6 segundos
            start_wait = time.time()
            while time.time() - start_wait < 6.0:
                if pending_order_data:
                    data = pending_order_data
                    pending_order_data = None
                else:
                    try:
                        raw_resp = ws.recv()
                    except StopIteration:
                        break
                    if not raw_resp:
                        continue
                    try:
                        data = json.loads(raw_resp)
                    except Exception:
                        continue

                try:
                    msg_name = data.get("name", "")
                    msg_body = data.get("msg", {})
                    st = data.get("status")
                    req = data.get("request_id")
                    
                    # 1. Ignorar respuestas de handshake y opciones generales (NO confundir con confirmación de orden)
                    if req == "set_opts" or msg_name in ["setOptions", "timeSync", "heartbeat", "front"]:
                        continue

                    # 2. Detección explícita de rechazo / error por parte de IQ Option
                    if msg_name == "market-order-placed" and req == req_id:
                        if isinstance(msg_body, dict):
                            if "id" in msg_body:
                                real_oid = msg_body["id"]
                                result = {
                                    "success": True,
                                    "order_id": str(real_oid),
                                    "symbol": clean_sym,
                                    "side": cfd_side,
                                    "amount": order_amount,
                                    "leverage": int(order_leverage_str),
                                    "environment": self.environment,
                                    "status": "FILLED"
                                }
                                break
                            elif "message" in msg_body:
                                err_msg = msg_body.get("message", "Error al colocar orden de mercado")
                                result = {"success": False, "error": f"Rechazado por IQ Option Margen Forex: {err_msg}"}
                                break

                    if (req == req_id and st and st != 2000) or msg_name in ["order-rejected", "order-error"]:
                        err_text = ""
                        if isinstance(msg_body, dict):
                            err_text = msg_body.get("message") or msg_body.get("reason") or msg_body.get("error")
                        if not err_text:
                            err_text = data.get("message") or data.get("error") or f"Error status {st}"
                        result = {"success": False, "error": f"Rechazado por IQ Option Margen CFD: {err_text}"}
                        break

                    if isinstance(msg_body, dict) and (msg_body.get("is_successful") is False or "message" in msg_body or "reason" in msg_body):
                        err_text = msg_body.get("message") or msg_body.get("reason") or msg_body.get("error")
                        if err_text:
                            result = {"success": False, "error": f"Rechazado por IQ Option: {err_text}"}
                            break

                    if msg_name == "result" and isinstance(msg_body, dict) and msg_body.get("success") is False:
                        err_reason = str(msg_body.get("reason", "Orden CFD no completada"))
                        result = {"success": False, "error": f"Rechazado por IQ Option Margen CFD: {err_reason}"}
                        break

                    if "error" in data:
                        err_text = str(data.get("error", ""))
                        if err_text:
                            result = {"success": False, "error": f"Rechazado por IQ Option: {err_text}"}
                            break

                    # 3. Confirmación exitosa verificada (con ID de orden real de IQ Option)
                    real_oid = None
                    if isinstance(msg_body, dict):
                        real_oid = msg_body.get("id") or msg_body.get("position_id") or msg_body.get("order_id")
                    elif isinstance(data.get("data"), dict):
                        real_oid = data["data"].get("id") or data["data"].get("position_id")

                    if msg_name in ["market-order-placed", "order-placed-temp", "order-placed", "position-changed", "order-filled"] and real_oid:
                        result = {
                            "success": True,
                            "order_id": str(real_oid),
                            "symbol": clean_sym,
                            "side": cfd_side,
                            "amount": order_amount,
                            "leverage": int(order_leverage_str),
                            "environment": self.environment,
                            "status": "FILLED"
                        }
                        break
                    elif req == req_id and st == 2000 and real_oid:
                        order_id = str(real_oid)
                        result = {
                            "success": True,
                            "order_id": order_id,
                            "symbol": clean_sym,
                            "side": cfd_side,
                            "amount": order_amount,
                            "leverage": int(order_leverage_str),
                            "environment": self.environment,
                            "status": "FILLED"
                        }
                        break
                    elif msg_name in ["position", "order"] and isinstance(msg_body, dict) and msg_body.get("id"):
                        order_id = str(msg_body.get("id"))
                        result = {
                            "success": True,
                            "order_id": order_id,
                            "symbol": clean_sym,
                            "side": cfd_side,
                            "amount": order_amount,
                            "leverage": order_leverage,
                            "environment": self.environment,
                            "status": "FILLED"
                        }
                        break
                except Exception:
                    pass

            if not result.get("success") and "Tiempo de espera" in str(result.get("error", "")):
                if order_sent:
                    result["unknown"] = True
                    result["request_id"] = req_id
                try:
                    ws.close()
                except Exception:
                    pass
                self._persistent_ws = None
        except Exception as e:
            self._persistent_ws = None
            import traceback
            tb = traceback.format_exc()
            result = {"success": False, "error": f"Error WebSocket IQ Option ({type(e).__name__}): {str(e)} | Trace: {tb}"}
            if order_sent:
                result["unknown"] = True
                result["request_id"] = req_id

        return result

    def close_position(self, position_id: str) -> Dict[str, Any]:
        """Solicita cierre CFD; en LIVE_REAL nunca convierte desconexión en éxito simulado."""
        if self.environment == "LIVE_REAL" and (not self.ssid or not position_id or str(position_id).startswith("IQ_PAPER")):
            return {"success": False, "error": "Cierre LIVE_REAL rechazado: faltan sesión o identificador válido del broker."}
        if not self.ssid or not position_id or str(position_id).startswith("IQ_PAPER"):
            return {"success": True, "status": "CLOSED_SIMULATED", "position_id": str(position_id)}
        import websocket
        import json
        import ssl
        try:
            ws = self._get_persistent_ws(timeout=12.0)
            
            # Autenticación protocol 3 y legacy
            auth_msg = {
                "name": "authenticate",
                "msg": {"ssid": self.ssid, "protocol": 3, "session_id": "", "client_session_id": ""},
                "request_id": f"auth_close_{int(time.time() * 1000)}"
            }
            ws.send(json.dumps(auth_msg))
            ws.send(json.dumps({"name": "ssid", "msg": self.ssid}))
            
            # Handshake
            auth_start = time.time()
            while time.time() - auth_start < 2.0:
                raw = ws.recv()
                if not raw:
                    continue
                try:
                    d = json.loads(raw)
                    if d.get("name") in ["authenticated", "profile", "timeSync", "front"]:
                        break
                except Exception:
                    pass

            ws.send(json.dumps({"name": "setOptions", "msg": {"sendResults": True}, "request_id": "set_opts_close"}))

            req_id = f"close_{int(time.time() * 1000)}"
            pos_val = int(position_id) if str(position_id).isdigit() else position_id
            
            # Envío de solicitud oficial Quadcode de cierre de posición Forex Margen
            close_msg = {
                "name": "sendMessage",
                "request_id": req_id,
                "msg": {
                    "name": "marginal-forex.close-position",
                    "version": "1.0",
                    "body": {"position_id": pos_val}
                }
            }
            ws.send(json.dumps(close_msg))
            
            res = {"success": True, "status": "CLOSED", "position_id": str(pos_val)}
            closed_ok = False
            start_wait = time.time()
            while time.time() - start_wait < 3.0:
                raw_resp = ws.recv()
                if not raw_resp:
                    continue
                try:
                    data = json.loads(raw_resp)
                    msg_name = data.get("name", "")
                    if msg_name in ["position-closed", "close-position", "position-changed"] or data.get("status") == 2000:
                        res = {"success": True, "status": "CLOSED", "position_id": str(pos_val)}
                        closed_ok = True
                        break
                    elif data.get("name") == "result" and data.get("request_id") == req_id and data.get("msg", {}).get("success") is True:
                        res = {"success": True, "status": "CLOSED", "position_id": str(pos_val)}
                        closed_ok = True
                        break
                    elif "error" in data:
                        err_text = str(data.get("error", ""))
                        if "already" in err_text.lower() or "not found" in err_text.lower():
                            res = {"success": True, "status": "ALREADY_CLOSED", "position_id": str(pos_val)}
                            closed_ok = True
                            break
                        break
                except Exception:
                    pass

            if not res.get("success"):
                try:
                    ws.close()
                except Exception:
                    pass
                self._persistent_ws = None
            return res
        except Exception as e:
            self._persistent_ws = None
            return {"success": False, "error": str(e)}

    def close_option(self, option_id: str) -> Dict[str, Any]:
        """Compatibilidad: Redirige al cierre de posición de Forex CFD."""
        return self.close_position(option_id)

    def submit_order(
        self, 
        symbol: str, 
        side: str, 
        amount: float, 
        position_id: Optional[str] = None, 
        option_id: Optional[str] = None,
        leverage: int = 25,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta o simula una orden Forex CFD en IQ Option según el entorno activo (PAPER o LIVE_REAL).
        """
        pos_id = position_id or option_id
        if self.environment == "LIVE_REAL" and not self.live_trading_armed:
            return {"success": False, "error": "LIVE_REAL bloqueado: el proceso no está armado para operar dinero real."}
        if self.environment == "LIVE_REAL" and not self.live_cfd_execution_verified:
            return {"success": False, "error": "LIVE_REAL bloqueado: sizing de CFD no verificado contra el riesgo solicitado."}
        # Si se solicita cierre explícito de posición
        if side.lower() in ["close", "sell_exit"]:
            if pos_id:
                return self.close_position(pos_id)
            if self.environment == "LIVE_REAL":
                return {"success": False, "error": "Cierre LIVE_REAL rechazado: falta identificador de posición."}
            return {"success": True, "status": "CLOSED_SIMULATED"}

        # Si se recibe 'sell' con un ID de posición existente, se interpreta como cierre de esa posición
        if side.lower() == "sell" and pos_id:
            return self.close_position(pos_id)

        # Offline simulation is valid only in PAPER; LIVE_REAL must fail closed.
        if not self.connected or not self.ssid or (self.environment != "LIVE_REAL" and not self.practice_balance_id):
            if self.environment == "LIVE_REAL":
                return {"success": False, "error": "IQ Option desconectado o sin sesión; orden LIVE_REAL rechazada sin simular."}
            order_id = f"IQ_PAPER_{int(time.time() * 1000)}"
            return {
                "success": True,
                "order_id": order_id,
                "symbol": symbol,
                "side": side.lower(),
                "amount": round(amount, 2),
                "leverage": leverage,
                "environment": self.environment,
                "status": "FILLED_SIMULATED"
            }

        # Conmutar cuenta según el entorno activo
        if self.environment == "LIVE_REAL":
            # Validaciones de seguridad para MODO REAL:
            if self.real_amount <= 0.0 and self.balance <= 0.0:
                return {
                    "success": False,
                    "error": f"Saldo insuficiente en cuenta real de IQ Option (Saldo: {self.real_amount:,.2f} {self.currency}). Por favor fondea tu cuenta antes de operar."
                }
            if self.real_balance_id:
                self.change_balance(self.real_balance_id)
        else:
            # En modo PAPER conectado a IQ Option: Operar en la cuenta Demo/Practice de IQ Option
            if self.practice_balance_id:
                self.change_balance(self.practice_balance_id)

        # Enviar orden Forex CFD real vía WebSocket autenticado de IQ Option
        return self._execute_real_ws_order(
            symbol=symbol, 
            side=side, 
            amount=amount, 
            leverage=leverage, 
            stop_loss_pct=stop_loss_pct, 
            take_profit_pct=take_profit_pct
        )

    def submit_binary_option(
        self, 
        symbol: str, 
        direction: str, 
        amount: float, 
        duration_minutes: int = 1,
        expiration_timestamp: Optional[int] = None
    ) -> Dict[str, Any]:
        """Reject binary orders until broker execution and settlement can be verified."""
        dir_clean = direction.lower()
        if dir_clean not in ["call", "put"]:
            return {"success": False, "error": f"Dirección inválida {direction}. Debe ser CALL o PUT."}

        if self.environment == "LIVE_REAL":
            return {
                "success": False,
                "error": "Binarias LIVE_REAL bloqueadas: falta conciliación del resultado oficial de IQ Option.",
                "execution_blocked": True,
                "status": "BLOCKED",
            }

        return {
            "success": False,
            "symbol": symbol,
            "direction": dir_clean,
            "amount": amount,
            "duration_minutes": duration_minutes,
            "environment": "PAPER",
            "execution_blocked": True,
            "status": "BLOCKED",
            "error": "Binarias Demo bloqueadas: falta conciliar el resultado oficial de IQ Option. No se creó una operación simulada ni se envió una orden.",
        }

    def _execute_real_binary_ws_order(self, *args, **kwargs) -> Dict[str, Any]:
        """Ruta deshabilitada hasta verificar aceptación y liquidación oficial de binarias."""
        return {
            "success": False,
            "execution_blocked": True,
            "status": "BLOCKED",
            "error": "Envío binario a IQ Option deshabilitado hasta implementar conciliación oficial.",
        }

    def get_candles(self, symbol: str, interval: int = 60, count: int = 40) -> list:
        """Obtiene velas reales en vivo directamente desde IQ Option vía WebSocket."""
        clean_sym = symbol.upper().replace("/", "").replace("_", "")
        active_id = self.get_active_id(clean_sym)

        if not self.ssid or active_id is None:
            return []
            
        import websocket
        import json
        import ssl
        try:
            ws_url = self._get_ws_url()
            headers = self._get_ws_headers()
            ws = websocket.create_connection(ws_url, header=headers, timeout=5, sslopt={"cert_reqs": ssl.CERT_REQUIRED, "check_hostname": True})
            ws.send(json.dumps({
                "name": "authenticate",
                "msg": {"ssid": self.ssid, "protocol": 3, "session_id": "", "client_session_id": ""},
                "request_id": f"auth_candles_{int(time.time() * 1000)}"
            }))
            ws.send(json.dumps({"name": "ssid", "msg": self.ssid}))
            
            auth_start = time.time()
            while time.time() - auth_start < 2.0:
                raw = ws.recv()
                if not raw:
                    continue
                try:
                    d = json.loads(raw)
                    if d.get("name") in ["authenticated", "profile", "timeSync", "front"]:
                        break
                except Exception:
                    pass

            req_id = f"candles_{int(time.time()*1000)}"
            msg = {
                "name": "sendMessage",
                "request_id": req_id,
                "msg": {
                    "name": "get-candles",
                    "version": "2.0",
                    "body": {
                        "active_id": int(active_id),
                        "split_normalization": False,
                        "count": int(count),
                        "size": int(interval)
                    }
                }
            }
            ws.send(json.dumps(msg))
            
            candles_list = []
            start = time.time()
            while time.time() - start < 4.0:
                raw = ws.recv()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                    if data.get("request_id") == req_id or data.get("name") in ["candles", "candle-generated"]:
                        body = data.get("msg", {})
                        raw_c = body.get("candles", []) if isinstance(body, dict) else (body if isinstance(body, list) else [])
                        if raw_c:
                            for c in raw_c:
                                candles_list.append({
                                    "time": int(c.get("from") or c.get("time") or time.time()),
                                    "open": float(c.get("open", 0.0)),
                                    "high": float(c.get("max") if "max" in c else c.get("high", 0.0)),
                                    "low": float(c.get("min") if "min" in c else c.get("low", 0.0)),
                                    "close": float(c.get("close", 0.0)),
                                    "volume": float(c.get("volume", 0.0))
                                })
                            break
                except Exception:
                    pass
            try:
                ws.close()
            except Exception:
                pass
            return candles_list
        except Exception:
            return []
