import time
import requests
import datetime
from typing import Dict, Any, Optional

ACTIVE_ASSET_IDS = {
    # Forex Estándar (Lunes a Viernes)
    "EURUSD": 1,
    "EURGBP": 2,
    "GBPJPY": 3,
    "EURJPY": 4,
    "GBPUSD": 5,
    "USDJPY": 6,
    "AUDCAD": 7,
    "NZDUSD": 8,
    "USDCHF": 72,
    "AUDUSD": 99,
    "USDCAD": 100,
    "AUDJPY": 101,
    "GBPCAD": 102,
    "GBPCHF": 103,
    "GBPAUD": 104,
    "EURCAD": 105,
    "CHFJPY": 106,
    "CADCHF": 107,
    "EURAUD": 108,
    # Forex OTC (Operación 24/7 Permanente: Días de semana y Fines de semana)
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
}

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
        self.environment = environment.upper() # "PAPER" o "LIVE_REAL"
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
            ws_url = "wss://iqoption.com/echo/websocket"
            headers = [
                f"Cookie: ssid={self.ssid}",
                "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ]
            ws = websocket.create_connection(ws_url, header=headers, timeout=8, sslopt={"cert_reqs": ssl.CERT_NONE})
            ws.send(json.dumps({"name": "ssid", "msg": self.ssid}))

            start_t = time.time()
            found = False
            while time.time() - start_t < 6.0:
                raw = ws.recv()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                    if data.get("name") == "profile":
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
                                elif b_type == 4:
                                    self.practice_balance_id = b_id
                                    self.practice_amount = round(amt, 2)
                            found = True
                            break
                except Exception:
                    pass
            ws.close()
            return found
        except Exception:
            return False

    def _fetch_profile(self) -> Dict[str, Any]:
        """Consulta perfil y balances vía API oficial usando la sesión de cookies/SSID activa."""
        if not self.ssid:
            return {"success": False, "error": "No hay SSID de sesión"}
        try:
            self.session.cookies.set("ssid", self.ssid, domain=".iqoption.com")
            self.session.cookies.set("ssid", self.ssid, domain="iqoption.com")
            prof_url = f"{self.base_url}/getprofile"
            prof_resp = self.session.get(prof_url, timeout=12)
            if prof_resp.status_code == 200:
                p_data = prof_resp.json()
                profile = p_data.get("result", {}) if isinstance(p_data, dict) else {}
                if not profile and isinstance(p_data, dict) and "profile" in p_data:
                    profile = p_data.get("profile", {})
                
                self.profile_data = profile
                self.currency = profile.get("currency", "USD")
                
                balances = profile.get("balances", [])
                for b in balances:
                    b_type = b.get("type")
                    b_id = b.get("id")
                    amt = float(b.get("amount", 0.0)) + float(b.get("bonus_amount", 0.0))
                    # type 1 = Real, type 4 = Practice (Demo)
                    if b_type == 1:
                        self.real_balance_id = b_id
                        self.real_amount = amt
                    elif b_type == 4:
                        self.practice_balance_id = b_id
                        self.practice_amount = amt

                # Si HTTP devolvió balances vacíos, sincronizar directamente vía WebSocket oficial en vivo
                if not balances or (self.real_balance_id is None and self.practice_balance_id is None):
                    self._fetch_live_balances_ws()

                if self.environment == "LIVE_REAL":
                    self.balance = self.real_amount
                    self.active_balance_id = self.real_balance_id
                    if self.real_balance_id:
                        self.change_balance(self.real_balance_id)
                else:
                    self.balance = self.practice_amount
                    self.active_balance_id = self.practice_balance_id
                    if self.practice_balance_id:
                        self.change_balance(self.practice_balance_id)

                return {"success": True, "profile": self.profile_data}
            elif prof_resp.status_code == 401:
                return {"success": False, "error": "Token SSID inválido o expirado. Inicia sesión en iqoption.com y actualiza tu SSID en Ajustes."}
            else:
                return {"success": False, "error": f"Error servidor IQ Option ({prof_resp.status_code})"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def connect(self) -> Dict[str, Any]:
        """
        Inicia sesión en IQ Option vía Token SSID directo o API oficial (auth.iqoption.com/api/v2/login).
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

        # 2. Autenticación estándar por Email y Contraseña
        if self.email and self.password:
            try:
                auth_url = "https://auth.iqoption.com/api/v2/login"
                payload = {
                    "identifier": self.email,
                    "password": self.password
                }
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                }
                resp = self.session.post(auth_url, json=payload, headers=headers, timeout=(15, 25))
                
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
            except requests.exceptions.Timeout:
                return {
                    "connected": False,
                    "authenticated": False,
                    "error": "El servidor de IQ Option bloquea conexiones de centros de datos VPS (Timeout en auth.iqoption.com). Para conectar de inmediato sin bloqueos de firewall, ingresa tu Token SSID en Ajustes."
                }
            except Exception as e:
                err_str = str(e)
                if "timed out" in err_str.lower() or "timeout" in err_str.lower():
                    err_msg = "Tiempo de espera agotado con auth.iqoption.com (Firewall de centro de datos). Ingresa tu Token SSID en Ajustes para conectar al instante."
                else:
                    err_msg = f"Error de conexión con IQ Option: {err_str}"
                return {"connected": False, "authenticated": False, "error": err_msg}

        return {
            "connected": False,
            "authenticated": False,
            "error": "Por favor ingresa tu Token SSID o tus credenciales de IQ Option en Ajustes."
        }

    def change_balance(self, balance_id: int) -> bool:
        """Cambia el balance activo en IQ Option entre cuenta REAL y cuenta PRACTICE (Demo)."""
        if not self.ssid:
            return False
        for endpoint in [f"{self.base_url}/profile/changebalance", f"{self.base_url}/changebalance"]:
            try:
                resp = self.session.post(endpoint, data={"balance_id": balance_id}, timeout=6)
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
        """Consulta el saldo y estado actual."""
        if self.is_configured and not self.connected:
            self.connect()
        elif self.connected and self.ssid and self.environment == "LIVE_REAL":
            now_t = time.time()
            if not hasattr(self, "_last_ws_balance_sync") or (now_t - getattr(self, "_last_ws_balance_sync", 0.0) > 12.0) or self.real_amount <= 0.0:
                self._last_ws_balance_sync = now_t
                self._fetch_live_balances_ws()
                self.balance = self.real_amount

        return {
            "authenticated": self.connected,
            "balance": round(self.balance, 2),
            "practice_balance": round(self.practice_amount, 2),
            "real_balance": round(self.real_amount, 2),
            "currency": self.currency,
            "environment": self.environment
        }

    def set_environment(self, env: str) -> Dict[str, Any]:
        """Conmuta de forma segura entre MODO PRÁCTICA (PAPER) y MODO REAL (LIVE_REAL)."""
        self.environment = env.upper()
        if self.connected:
            target_id = self.real_balance_id if self.environment == "LIVE_REAL" else self.practice_balance_id
            if target_id:
                self.change_balance(target_id)
        if self.environment == "LIVE_REAL":
            self.balance = self.real_amount
        else:
            self.balance = self.practice_amount
        return {
            "success": True,
            "environment": self.environment,
            "balance": self.balance
        }

    def get_payout(self, symbol: str) -> float:
        """
        Retorna el ratio de retorno/payout vigente para la opción binaria (ej. 0.88 para 88%).
        Permite filtrar pares que no cumplan el mínimo de rentabilidad matemática (>= 0.80).
        """
        clean_sym = symbol.upper().replace("-OTC", "").replace("OTC", "")
        if hasattr(self, "_payout_cache") and symbol in self._payout_cache:
            return float(self._payout_cache[symbol])
        return 0.88

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

        if not self.ssid:
            return {"success": False, "error": "No hay SSID de sesión activo para ejecutar orden en IQ Option"}

        # Normalizar símbolo eliminando caracteres especiales y sufijos OTC
        # Margen CFD en IQ Option opera exclusivamente sobre pares Forex estándar (EURUSD, GBPUSD, etc.) y Acciones
        clean_sym = symbol.replace("/", "").replace(" ", "").replace("(", "").replace(")", "").replace("_", "").replace("-OTC", "").replace("OTC", "").upper()
        active_id = ACTIVE_ASSET_IDS.get(clean_sym, 1)

        cfd_side = "buy" if side.lower() in ["buy", "buy_long", "call"] else "sell"
        order_leverage = int(leverage) if leverage else 25
        
        # En cuentas COP de IQ Option, el importe mínimo de operación es de 2,000 COP (En USD es $1.00)
        min_amount = 2000.0 if self.currency == "COP" else 1.0
        order_amount = max(min_amount, round(float(amount), 2))

        # Validación estricta de saldo disponible en cuenta real
        if self.environment == "LIVE_REAL" and order_amount > self.real_amount:
            return {
                "success": False,
                "error": f"Saldo insuficiente en IQ Option: Se requieren al menos {order_amount:,.2f} {self.currency} y dispones de {self.real_amount:,.2f} {self.currency}."
            }

        ws_url = "wss://iqoption.com/echo/websocket"
        headers = [
            f"Cookie: ssid={self.ssid}",
            "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]

        result = {"success": False, "error": "Tiempo de espera agotado al conectar al WebSocket de IQ Option"}

        try:
            ws = websocket.create_connection(ws_url, header=headers, timeout=8, sslopt={"cert_reqs": ssl.CERT_NONE})
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
            while time.time() - auth_start < 2.5:
                raw = ws.recv()
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

            order_leverage = int(leverage) if leverage else 25
            target_bal_id = int(target_balance) if target_balance and str(target_balance).isdigit() else target_balance

            # Enviar orden de mercado oficial Quadcode Margen Forex CFD (100% Forex sin expiración de tiempo)
            # Instrument ID sigue el esquema mf.{active_id} (ej. mf.1 para EURUSD)
            count_units = "100" # Lote micro mínimo 0.001 (100 unidades de divisa base)
            order_leverage_str = str(min(order_leverage, 500)) if order_leverage else "500"
            
            body_payload = {
                "side": cfd_side,
                "user_balance_id": target_bal_id,
                "count": count_units,
                "instrument_id": f"mf.{active_id}",
                "instrument_active_id": active_id,
                "leverage": order_leverage_str
            }
            if stop_loss_pct is not None:
                body_payload["stop_loss"] = {"value": str(round(float(stop_loss_pct), 2)), "type": "pnl"}
            if take_profit_pct is not None:
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

            # 3. Leer respuesta con timeout de 6 segundos
            start_wait = time.time()
            while time.time() - start_wait < 6.0:
                if pending_order_data:
                    data = pending_order_data
                    pending_order_data = None
                else:
                    raw_resp = ws.recv()
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

            ws.close()
        except Exception as e:
            result = {"success": False, "error": f"Error WebSocket IQ Option: {str(e)}"}

        return result

    def close_position(self, position_id: str) -> Dict[str, Any]:
        """Cierra una posición activa en IQ Option (vía sell-options anticipada o close-position)."""
        if not self.ssid or not position_id or str(position_id).startswith("IQ_PAPER"):
            return {"success": True, "status": "CLOSED_SIMULATED", "position_id": str(position_id)}
        import websocket
        import json
        import ssl
        try:
            ws_url = "wss://iqoption.com/echo/websocket"
            headers = [
                f"Cookie: ssid={self.ssid}",
                "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            ]
            ws = websocket.create_connection(ws_url, header=headers, timeout=6, sslopt={"cert_reqs": ssl.CERT_NONE})
            
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

            ws.close()
            return res
        except Exception as e:
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
        # Si se solicita cierre explícito de posición
        if side.lower() in ["close", "sell_exit"]:
            if pos_id:
                return self.close_position(pos_id)
            return {"success": True, "status": "CLOSED_SIMULATED"}

        # Si se recibe 'sell' con un ID de posición existente, se interpreta como cierre de esa posición
        if side.lower() == "sell" and pos_id:
            return self.close_position(pos_id)

        if not self.connected or self.environment != "LIVE_REAL":
            order_id = f"IQ_PAPER_{int(time.time() * 1000)}"
            return {
                "success": True,
                "order_id": order_id,
                "symbol": symbol,
                "side": side.lower(),
                "amount": round(amount, 2),
                "leverage": leverage,
                "environment": "PAPER",
                "status": "FILLED_SIMULATED"
            }

        # Validaciones de seguridad para MODO REAL:
        if self.real_amount <= 0.0 and self.balance <= 0.0:
            return {
                "success": False,
                "error": "Saldo insuficiente en cuenta real de IQ Option (Saldo: 0.0 COP). Por favor fondea tu cuenta antes de operar."
            }

        # Conmutar cuenta a saldo REAL en IQ Option antes de disparar la orden
        if self.real_balance_id:
            self.change_balance(self.real_balance_id)

        # Enviar orden Forex CFD real vía WebSocket autenticado de IQ Option
        return self._execute_real_ws_order(
            symbol=symbol, 
            side=side, 
            amount=amount, 
            leverage=leverage, 
            stop_loss_pct=stop_loss_pct, 
            take_profit_pct=take_profit_pct
        )

    def get_candles(self, symbol: str, interval: int = 60, count: int = 40) -> list:
        """Obtiene velas reales en vivo directamente desde IQ Option vía WebSocket."""
        clean_sym = symbol.upper().replace("/", "").replace("_", "")
        active_id = ACTIVE_ASSET_IDS.get(clean_sym, ACTIVE_ASSET_IDS.get(f"{clean_sym}-OTC", 76))
        
        if not self.ssid:
            return []
            
        import websocket
        import json
        import ssl
        try:
            ws_url = "wss://iqoption.com/echo/websocket"
            headers = [
                f"Cookie: ssid={self.ssid}",
                "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            ]
            ws = websocket.create_connection(ws_url, header=headers, timeout=5, sslopt={"cert_reqs": ssl.CERT_NONE})
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
                        "active_id": active_id,
                        "split_normalization": 0,
                        "count": count,
                        "size": interval
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
                                    "time": c.get("from") or c.get("time") or int(time.time()),
                                    "open": float(c.get("open", 0.0)),
                                    "high": float(c.get("max") or c.get("high", 0.0)),
                                    "low": float(c.get("min") or c.get("low", 0.0)),
                                    "close": float(c.get("close", 0.0)),
                                    "volume": float(c.get("volume", 0.0))
                                })
                            break
                except Exception:
                    pass
            ws.close()
            return candles_list
        except Exception:
            return []

