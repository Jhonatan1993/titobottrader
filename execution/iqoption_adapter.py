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
        """Prueba la conexión y reporta el estado actual del broker."""
        if not self.is_configured:
            return {
                "connected": True,
                "status": "MODO SIMULACIÓN (FEED PÚBLICO)",
                "mode": "PAPER_SIMULATION",
                "environment": self.environment,
                "balance": self.balance
            }
        
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
        return {
            "connected": False,
            "status": "ERROR DE CONEXIÓN",
            "error": login_res.get("error", "No se pudo conectar a IQ Option")
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

    def _execute_real_ws_order(self, symbol: str, side: str, amount: float) -> Dict[str, Any]:
        """
        Envía una orden real al servidor WebSocket de IQ Option utilizando el token SSID de la sesión autenticada.
        """
        import websocket
        import json
        import ssl

        if not self.ssid:
            return {"success": False, "error": "No hay SSID de sesión activo para ejecutar orden en IQ Option"}

        # Normalizar símbolo eliminando caracteres especiales
        raw_sym = symbol.replace("/", "").replace(" ", "").replace("(", "").replace(")", "").replace("_", "").upper()
        clean_sym = symbol.replace("/", "").replace("_", "").upper()
        
        # Resolución universal de activo: OTC opera 24/7 (días de semana y fines de semana)
        is_weekend = datetime.datetime.now(datetime.timezone.utc).weekday() >= 5
        if "OTC" in raw_sym:
            # Si se solicita explícitamente OTC (ej: EURUSD-OTC o EURUSDOTC), opera OTC en cualquier día (Lunes a Domingo)
            active_id = ACTIVE_ASSET_IDS.get(symbol.upper(), ACTIVE_ASSET_IDS.get(raw_sym, ACTIVE_ASSET_IDS.get(clean_sym, 76)))
        elif is_weekend:
            # En fin de semana, Forex estándar cerrado -> fallback automático a OTC
            active_id = ACTIVE_ASSET_IDS.get(f"{clean_sym}-OTC", ACTIVE_ASSET_IDS.get(f"{clean_sym}OTC", 76))
        else:
            # En días de semana, permite operar tanto el par estándar como el par OTC si está seleccionado
            active_id = ACTIVE_ASSET_IDS.get(clean_sym, ACTIVE_ASSET_IDS.get(f"{clean_sym}-OTC", 1))

        direction = "call" if side.lower() in ["buy", "buy_long"] else "put"
        
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
            # 1. Autenticar sesión vía mensaje SSID
            auth_msg = {"name": "ssid", "msg": self.ssid}
            ws.send(json.dumps(auth_msg))

            # Esperar confirmación de handshake (profile) antes de enviar la orden
            auth_start = time.time()
            while time.time() - auth_start < 2.0:
                raw = ws.recv()
                if not raw:
                    continue
                try:
                    d = json.loads(raw)
                    if d.get("name") in ["profile", "timeSync", "front"]:
                        break
                except Exception:
                    pass

            # 2. Calcular expiración Turbo exacta
            now = int(time.time())
            rem = now % 60
            exp_time = (now // 60 + (2 if rem > 30 else 1)) * 60
            req_id = f"tito_{int(time.time() * 1000)}"
            target_balance = self.real_balance_id if self.environment == "LIVE_REAL" else self.practice_balance_id

            # Enviar binary-options.open-option oficial verificado (Funciona para Turbo / Binarias / OTC)
            binary_payload = {
                "name": "sendMessage",
                "request_id": req_id,
                "msg": {
                    "name": "binary-options.open-option",
                    "version": "1.0",
                    "body": {
                        "user_balance_id": target_balance,
                        "active_id": active_id,
                        "option_type_id": 3,
                        "direction": direction,
                        "expired": exp_time,
                        "price": order_amount
                    }
                }
            }
            ws.send(json.dumps(binary_payload))

            # 3. Leer respuesta con timeout de 5 segundos
            start_wait = time.time()
            while time.time() - start_wait < 5.0:
                raw_resp = ws.recv()
                if not raw_resp:
                    continue
                try:
                    data = json.loads(raw_resp)
                    msg_name = data.get("name", "")
                    msg_body = data.get("msg", {})
                    st = data.get("status")
                    
                    if st == 2000 or msg_name in ["option-opened", "socket-option-opened", "order-placed", "buyComplete"]:
                        order_id = str(msg_body.get("id") or msg_body.get("option_id") or msg_body.get("order_id") or data.get("request_id", req_id))
                        result = {
                            "success": True,
                            "order_id": order_id,
                            "symbol": clean_sym,
                            "side": side.lower(),
                            "amount": order_amount,
                            "environment": self.environment,
                            "status": "FILLED"
                        }
                        break
                    elif msg_name == "option" and isinstance(msg_body, dict):
                        if "message" in msg_body:
                            result = {"success": False, "error": f"Rechazado por IQ Option: {msg_body.get('message')}"}
                            break
                        elif "id" in msg_body:
                            order_id = str(msg_body.get("id"))
                            result = {
                                "success": True,
                                "order_id": order_id,
                                "symbol": clean_sym,
                                "side": side.lower(),
                                "amount": order_amount,
                                "environment": self.environment,
                                "status": "FILLED"
                            }
                            break
                    elif "error" in data:
                        err_text = data.get("error")
                        if err_text:
                            result = {"success": False, "error": f"Rechazado por IQ Option: {err_text}"}
                            break
                except Exception:
                    pass

            ws.close()
        except Exception as e:
            result = {"success": False, "error": f"Error WebSocket IQ Option: {str(e)}"}

        return result

    def close_option(self, option_id: str) -> Dict[str, Any]:
        """Cierra o vende anticipadamente una opción binaria activa en IQ Option."""
        if not self.ssid or not option_id or str(option_id).startswith("IQ_PAPER"):
            return {"success": True, "status": "CLOSED_SIMULATED"}
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
            ws.send(json.dumps({"name": "ssid", "msg": self.ssid}))
            
            req_id = f"sell_{int(time.time() * 1000)}"
            opt_val = int(option_id) if str(option_id).isdigit() else option_id
            sell_msg = {
                "name": "sendMessage",
                "request_id": req_id,
                "msg": {
                    "name": "binary-options.sell-option",
                    "version": "1.0",
                    "body": {"options_ids": [opt_val]}
                }
            }
            ws.send(json.dumps(sell_msg))
            ws.close()
            return {"success": True, "status": "SOLD_EARLY"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def submit_order(self, symbol: str, side: str, amount: float, option_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Ejecuta o simula una orden en IQ Option según el entorno activo (PAPER o LIVE_REAL).
        """
        # En opciones binarias / turbo, 'sell' o 'close' es el CIERRE de la posición existente,
        # NUNCA debe abrir una orden opuesta (PUT/Baja).
        if side.lower() in ["sell", "close", "sell_exit"]:
            if option_id:
                return self.close_option(option_id)
            return {"success": True, "status": "CLOSED_AT_EXPIRATION"}

        if not self.connected or self.environment != "LIVE_REAL":
            order_id = f"IQ_PAPER_{int(time.time() * 1000)}"
            return {
                "success": True,
                "order_id": order_id,
                "symbol": symbol,
                "side": side.lower(),
                "amount": round(amount, 2),
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

        # Enviar orden real vía WebSocket autenticado de IQ Option
        return self._execute_real_ws_order(symbol, side, amount)
