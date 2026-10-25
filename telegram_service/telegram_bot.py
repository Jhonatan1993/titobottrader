import os
import time
import logging
import threading
import requests
import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger("TelegramService")

class TelegramService:
    """
    Controlador y Sistema de Notificaciones Bidireccional por Telegram:
    - Alertas en tiempo real al abrir y cerrar operaciones (con métricas SMC, RSI, ADX).
    - Escuchador asíncrono de comandos interactivos (/status, /pause, /resume, /reset, /report, /stop).
    - Generación y envío automatizado de Reportes Ejecutivos diarios a las 23:55 con archivo CSV adjunto.
    - Hilos independientes (Daemon) para no bloquear ni retardar el ciclo de trading del motor.
    """
    _instance: Optional['TelegramService'] = None

    @classmethod
    def get_instance(cls, engine=None) -> 'TelegramService':
        if cls._instance is None:
            cls._instance = TelegramService(engine)
        elif engine and not cls._instance.engine:
            cls._instance.engine = engine
        return cls._instance

    def __init__(self, engine=None):
        self.engine = engine
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        self.base_url = f"https://api.telegram.org/bot{self.token}" if self.token else ""
        self.enabled = bool(self.token and self.chat_id)
        
        self.last_update_id = 0
        self._is_listening = False
        self._last_report_date = ""

        if self.enabled:
            logger.info("🤖 Servicio de Telegram habilitado y configurado.")
            self.start_listener()
            self.start_scheduler()
        else:
            logger.info("ℹ️ Telegram no configurado. Para activarlo defina TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en variables de entorno o archivo .env.")

    # -------------------------------------------------------------
    # Envío de Mensajes y Documentos Asíncronos
    # -------------------------------------------------------------
    def send_message(self, text: str):
        if not self.enabled:
            return
        threading.Thread(target=self._send_sync, args=(text,), daemon=True).start()

    def _send_sync(self, text: str):
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
            requests.post(url, json=payload, timeout=8)
        except Exception as e:
            logger.debug(f"Error enviando mensaje a Telegram: {e}")

    def send_document(self, file_path: str, caption: str = ""):
        if not self.enabled or not os.path.exists(file_path):
            return
        threading.Thread(target=self._send_doc_sync, args=(file_path, caption), daemon=True).start()

    def _send_doc_sync(self, file_path: str, caption: str):
        try:
            url = f"{self.base_url}/sendDocument"
            with open(file_path, "rb") as doc:
                files = {"document": doc}
                data = {
                    "chat_id": self.chat_id,
                    "caption": caption,
                    "parse_mode": "HTML"
                }
                requests.post(url, data=data, files=files, timeout=25)
        except Exception as e:
            logger.debug(f"Error enviando documento a Telegram: {e}")

    # -------------------------------------------------------------
    # Notificaciones de Operaciones
    # -------------------------------------------------------------
    def notify_startup(self, balance: float, environment: str = "PAPER"):
        env_badge = "🟢 ENTORNO DE PRUEBAS (PAPER)" if environment == "PAPER" else "🔴 ENTORNO REAL (LIVE)"
        msg = (
            f"🚀 <b>TITOBOTTRADER 24/7 INICIADO</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🛡 <b>Modo:</b> <code>{env_badge}</code>\n"
            f"💰 <b>Balance Inicial:</b> <code>${balance:,.2f} USD</code>\n"
            f"🧠 <b>Estrategia:</b> <code>Smart Money Concepts (SMC) + Reversión</code>\n"
            f"📊 <b>Filtros:</b> ForexFactory XML ±15m + Segundo 58 + Anti-Racha\n"
            f"<i>Comandos disponibles: /status | /pause | /resume | /reset | /report | /stop</i>"
        )
        self.send_message(msg)

    def notify_entry(self, symbol: str, direction: str, stake: float, reason: str, rsi: float = 50.0, adx: float = 0.0, payout: float = 0.85):
        arrow = "🟢 CALL (Compra)" if direction.upper() == "CALL" else "🔴 PUT (Venta)"
        msg = (
            f"⚡ <b>OPERACIÓN EJECUTADA [IQ OPTION]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔹 <b>Activo:</b> <code>{symbol}</code>\n"
            f"🎯 <b>Dirección:</b> <b>{arrow}</b>\n"
            f"💵 <b>Inversión:</b> <code>${stake:,.2f} USD</code> (Payout: {int(payout * 100)}%)\n"
            f"🔍 <b>Tesis:</b> <i>{reason}</i>\n"
            f"📊 <b>Confluencia:</b> RSI: <code>{rsi:.1f}</code> | ADX: <code>{adx:.1f}</code>\n"
            f"⏱ <b>Expiración:</b> 60 segundos (Turbo 1m)"
        )
        self.send_message(msg)

    def notify_result(self, symbol: str, outcome: str, profit: float, daily_pnl: float, consecutive_losses: int = 0):
        if outcome == "WIN":
            header = "✅ <b>OPERACIÓN GANADA (ITM)</b>"
            badge = "🏆"
        elif outcome == "LOSS":
            header = "❌ <b>OPERACIÓN PERDIDA (OTM)</b>"
            badge = "⚠️"
        else:
            header = "⚖️ <b>OPERACIÓN EMPATADA (ATM)</b>"
            badge = "⚪"

        pnl_symbol = "+" if profit > 0 else ""
        msg = (
            f"{header}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔹 <b>Activo:</b> <code>{symbol}</code>\n"
            f"{badge} <b>Resultado:</b> <code>{pnl_symbol}${profit:,.2f} USD</code>\n"
            f"📈 <b>PnL Diario Acumulado:</b> <code>{daily_pnl:+,.2f} USD</code>\n"
            f"🛡 <b>Racha Negativa:</b> <code>{consecutive_losses}/3</code>"
        )
        self.send_message(msg)

    # -------------------------------------------------------------
    # Reportes Diarios con Archivo CSV Adjunto
    # -------------------------------------------------------------
    def send_daily_audit_report(self, trigger_reason: str = "Cierre de Jornada"):
        if not self.enabled:
            return
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # Buscar el archivo CSV de historial de operaciones
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        csv_path = os.path.join(base_dir, "data", "trades_history.csv")

        status_text = "Sin datos de auditoría disponibles."
        if self.engine:
            state = self.engine.get_state()
            wallet = state.get("wallets", {}).get("IQOPTION", {})
            bal = wallet.get("cash", 0.0)
            pnl = wallet.get("daily_pnl", 0.0)
            status_text = (
                f"💰 <b>Balance Actual:</b> <code>${bal:,.2f} USD</code>\n"
                f"📈 <b>PnL Sesión:</b> <code>{pnl:+,.2f} USD</code>\n"
                f"📋 <b>Operaciones Registradas:</b> <code>{len(state.get('completed_trades', []))}</code>"
            )

        caption = (
            f"📊 <b>REPORTE EJECUTIVO DIARIO ({today_str})</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"ℹ️ <i>Evento: {trigger_reason}</i>\n"
            f"{status_text}\n"
            f"📎 <i>Archivo de auditoría institucional adjunto.</i>"
        )

        if os.path.exists(csv_path):
            self.send_document(csv_path, caption)
        else:
            self.send_message(caption)

    # -------------------------------------------------------------
    # Escuchador Asíncrono de Comandos (Bidireccional)
    # -------------------------------------------------------------
    def start_listener(self):
        if self._is_listening or not self.enabled:
            return
        self._is_listening = True
        threading.Thread(target=self._listen_loop, daemon=True, name="TelegramListener").start()

    def _listen_loop(self):
        while self._is_listening:
            try:
                url = f"{self.base_url}/getUpdates"
                params = {"offset": self.last_update_id + 1, "timeout": 20}
                res = requests.get(url, params=params, timeout=25)
                if res.status_code == 200:
                    data = res.json()
                    for item in data.get("result", []):
                        self.last_update_id = item.get("update_id", self.last_update_id)
                        message = item.get("message", {})
                        from_chat = str(message.get("chat", {}).get("id", ""))
                        text = message.get("text", "").strip()

                        # Validación de seguridad: solo responder al Chat ID del propietario
                        if from_chat == self.chat_id and text:
                            self._handle_command(text)
            except Exception as e:
                logger.debug(f"Error en listener de Telegram: {e}")
            time.sleep(1)

    def _handle_command(self, cmd_text: str):
        cmd = cmd_text.split()[0].lower()
        if cmd in ("/start", "/help"):
            msg = (
                "🎮 <b>PANEL DE CONTROL TITOBOTTRADER</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "<b>Comandos Disponibles:</b>\n"
                "🔹 /status - Estado del bot, balance, PnL y operaciones en curso\n"
                "🔹 /pause - Pausar temporalmente el escaneo de operaciones\n"
                "🔹 /resume - Reanudar el escaneo y operativa automática\n"
                "🔹 /reset - Reiniciar contadores diarios de PnL y rachas a cero\n"
                "🔹 /report - Generar y descargar el reporte CSV de operaciones\n"
                "🔹 /stop - Parada de emergencia inmediata\n"
            )
            self.send_message(msg)

        elif cmd == "/status":
            if not self.engine:
                self.send_message("ℹ️ Motor de trading no vinculado al listener.")
                return
            state = self.engine.get_state()
            wallet = state.get("wallets", {}).get("IQOPTION", {})
            bin_stat = state.get("binary_options", {})
            is_running = self.engine.is_running
            run_status = "🟢 OPERANDO" if is_running else "⏸️ EN PAUSA"
            
            msg = (
                f"📊 <b>ESTADO EN VIVO DEL SISTEMA</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⚡ <b>Estado Motor:</b> <code>{run_status}</code>\n"
                f"💰 <b>Balance:</b> <code>${wallet.get('cash', 0.0):,.2f} USD</code>\n"
                f"📈 <b>PnL Realizado:</b> <code>{wallet.get('realized_pnl', 0.0):+,.2f} USD</code>\n"
                f"🎯 <b>Win Rate:</b> <code>{bin_stat.get('win_rate', 0)}%</code> "
                f"({bin_stat.get('total_wins', 0)}W / {bin_stat.get('total_losses', 0)}L)\n"
                f"⏱ <b>Operación Activa:</b> <code>{bin_stat.get('has_active_trade', False)}</code>"
            )
            self.send_message(msg)

        elif cmd == "/pause":
            if self.engine:
                self.engine.is_running = False
                self.send_message("⏸️ <b>MOTOR PAUSADO</b>: No se abrirán nuevas operaciones hasta reanudar con /resume.")

        elif cmd == "/resume":
            if self.engine:
                self.engine.is_running = True
                self.send_message("▶️ <b>MOTOR REANUDADO</b>: Escaneo institucional activo.")

        elif cmd == "/reset":
            if self.engine and hasattr(self.engine, "binary_engine") and hasattr(self.engine.binary_engine, "soros_manager"):
                self.engine.binary_engine.soros_manager.manual_reset()
            self.send_message("🔄 <b>CONTADORES REINICIADOS</b>: PnL diario y rachas negativas restablecidos a cero.")

        elif cmd == "/report":
            self.send_daily_audit_report("Solicitud Manual de Usuario vía /report")

        elif cmd == "/stop":
            if self.engine:
                self.engine.is_running = False
                self.send_message("🛑 <b>PARADA DE EMERGENCIA</b>: Motor detenido preventivamente.")

    # -------------------------------------------------------------
    # Programador Diario (23:55 Reporte)
    # -------------------------------------------------------------
    def start_scheduler(self):
        threading.Thread(target=self._scheduler_loop, daemon=True, name="TelegramScheduler").start()

    def _scheduler_loop(self):
        while True:
            try:
                now = datetime.datetime.now()
                # A las 23:55 enviar el reporte diario automático
                if now.hour == 23 and now.minute == 55:
                    today_str = now.strftime("%Y-%m-%d")
                    if self._last_report_date != today_str:
                        self.send_daily_audit_report("Cierre Automático de Jornada (23:55)")
                        self._last_report_date = today_str
            except Exception as e:
                logger.debug(f"Error en scheduler de Telegram: {e}")
            time.sleep(45)
