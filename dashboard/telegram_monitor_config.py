"""Configuration helpers for the independent Telegram monitor.

This module does not import or control the trading engine.
"""
import fcntl
import json
import os
import re
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

CONFIG_PATH = Path("/etc/titobot-monitor/telegram.env")
LOCK_PATH = Path("/etc/titobot-monitor/config.lock")
SERVICE = "titobot-monitor.service"
TOKEN_PATTERN = re.compile(r"[0-9]{1,20}:[A-Za-z0-9_-]{1,200}\Z")
CHAT_PATTERN = re.compile(r"[1-9][0-9]{0,19}\Z")


class ConfigurationError(Exception):
    """A safe, non-secret configuration error."""


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ConfigurationError("Telegram respondió con una redirección no permitida.")


def telegram_call(token, method, payload=None):
    request = Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        # The token is part of the URL: never forward it to a redirect or
        # an inherited proxy. TLS certificate validation remains enabled.
        opener = build_opener(ProxyHandler({}), RejectRedirects())
        with opener.open(request, timeout=10) as response:
            result = json.load(response)
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise ConfigurationError("Telegram rechazó la solicitud.")
        return result.get("result")
    except ConfigurationError:
        raise
    except Exception:
        # HTTP exceptions can include the token in their URL.
        raise ConfigurationError("No se pudo contactar con Telegram.") from None


def validate_token(token):
    if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
        raise ConfigurationError("El formato del token no es válido.")


def discover_chats(token, api=telegram_call):
    validate_token(token)
    bot = api(token, "getMe")
    webhook = api(token, "getWebhookInfo")
    if not isinstance(bot, dict) or not isinstance(bot.get("username"), str):
        raise ConfigurationError("No se pudo identificar el bot.")
    if not isinstance(webhook, dict) or webhook.get("url"):
        raise ConfigurationError("El bot tiene un webhook activo; no se ha modificado.")
    updates = api(token, "getUpdates", {"limit": 100, "timeout": 0})
    if not isinstance(updates, list):
        raise ConfigurationError("Respuesta inesperada de Telegram.")
    chats = {}
    for update in updates:
        message = update.get("message", {}) if isinstance(update, dict) else {}
        chat = message.get("chat", {}) if isinstance(message, dict) else {}
        if not isinstance(chat, dict) or chat.get("type") != "private":
            continue
        ident = chat.get("id")
        if isinstance(ident, int) and not isinstance(ident, bool) and ident > 0:
            chats[str(ident)] = str(chat.get("first_name") or "Chat privado")[:60]
    return {"bot": bot["username"], "chats": [{"id": ident, "name": name} for ident, name in chats.items()]}


def _read_existing(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        raise ConfigurationError("La configuración existente no es un archivo regular.")
    return path.read_bytes()


def _atomic_write(path, content):
    fd, temporary = tempfile.mkstemp(prefix=".telegram-config-", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def restart_monitor():
    try:
        subprocess.run(["systemctl", "restart", SERVICE], check=True, timeout=20, capture_output=True)

        def current_pid():
            state = subprocess.run(
                ["systemctl", "show", SERVICE, "--property=ActiveState", "--property=MainPID"],
                check=True, timeout=10, capture_output=True, text=True,
            )
            values = dict(line.split("=", 1) for line in state.stdout.splitlines() if "=" in line)
            if values.get("ActiveState") != "active" or not values.get("MainPID", "").isdigit():
                raise ConfigurationError("No se pudo confirmar el estado del monitor.")
            pid = int(values["MainPID"])
            if pid <= 0:
                raise ConfigurationError("No se pudo confirmar el estado del monitor.")
            return pid

        initial_pid = current_pid()
        time.sleep(3)
        if current_pid() != initial_pid:
            raise ConfigurationError("El monitor se reinició inesperadamente.")
    except (OSError, subprocess.SubprocessError):
        raise ConfigurationError("No se pudo iniciar el monitor de Telegram.") from None


def configure(token, chat_id, config_path=CONFIG_PATH, lock_path=LOCK_PATH,
              api=telegram_call, restart=restart_monitor):
    validate_token(token)
    chat_id = str(chat_id)
    if not CHAT_PATTERN.fullmatch(chat_id):
        raise ConfigurationError("Selecciona un chat privado válido.")
    # Confirm the target is private and Telegram accepted a test before replacing anything.
    chat = api(token, "getChat", {"chat_id": chat_id})
    if not isinstance(chat, dict) or chat.get("type") != "private" or str(chat.get("id")) != chat_id:
        raise ConfigurationError("El destino debe ser un chat privado válido.")
    api(token, "sendMessage", {
        "chat_id": chat_id,
        "text": "Prueba de reconexión de alertas TitoBot. No se ha realizado ninguna operación.",
    })

    config_path = Path(config_path)
    lock_path = Path(lock_path)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = _read_existing(config_path)
        new = f"TELEGRAM_BOT_TOKEN={token}\nTELEGRAM_CHAT_ID={chat_id}\n".encode("utf-8")
        _atomic_write(config_path, new)
        try:
            restart()
        except Exception:
            try:
                if previous is None:
                    config_path.unlink(missing_ok=True)
                else:
                    _atomic_write(config_path, previous)
                    restart()
            except Exception:
                raise ConfigurationError(
                    "Falló el monitor y no se pudo confirmar la restauración; requiere revisión."
                ) from None
            if previous is None:
                raise ConfigurationError("Falló el monitor; se retiró la configuración nueva, pero el estado del servicio requiere revisión.") from None
            raise ConfigurationError("Falló el monitor; se restauró la configuración anterior y se solicitó su reinicio.") from None
