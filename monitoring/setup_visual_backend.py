#!/usr/bin/env python3
"""Private, line-oriented setup backend. Input contains secrets; output never does."""
import json
import os
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen

CONFIG = Path("/etc/titobot-monitor/telegram.env")


def api(token, method, payload=None):
    request = Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=15) as response:
        result = json.load(response)
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise ValueError("Telegram rejected the request")
    return result.get("result")


def emit(value):
    print(json.dumps(value, ensure_ascii=True), flush=True)


def main():
    if os.geteuid() != 0 or CONFIG.exists() or CONFIG.is_symlink():
        emit({"error": "La configuración ya existe o faltan permisos; no se ha modificado."})
        return 1
    try:
        request = json.loads(sys.stdin.readline())
        token = request.get("token", "").strip()
        if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token):
            emit({"error": "El formato del token no es válido. Copia solo el token completo."})
            return 1
        bot = api(token, "getMe")
        if not isinstance(bot, dict) or not bot.get("username"):
            raise ValueError("Invalid bot identity")
        webhook = api(token, "getWebhookInfo")
        if not isinstance(webhook, dict) or webhook.get("url"):
            emit({"error": "El bot tiene un webhook activo; no se ha modificado."})
            return 1
        updates = api(token, "getUpdates", {"limit": 100, "timeout": 0})
        if not isinstance(updates, list):
            raise ValueError("Invalid response")
        chats = {}
        private_messages = 0
        for item in updates:
            message = item.get("message", {}) if isinstance(item, dict) else {}
            chat = message.get("chat", {}) if isinstance(message, dict) else {}
            if not isinstance(chat, dict) or chat.get("type") != "private":
                continue
            private_messages += 1
            ident = chat.get("id")
            if isinstance(ident, int) and not isinstance(ident, bool) and ident > 0:
                chats[ident] = str(chat.get("first_name", "Chat privado")).replace("\n", " ")[:60]
        if not chats:
            username = str(bot["username"])
            emit({"error": f"Bot @{username}: no hay mensajes privados pendientes ({len(updates)} actualizaciones, {private_messages} privadas). Envía un mensaje a este bot y vuelve a buscar. Otro proceso podría haber leído las actualizaciones."})
            return 1
        options = list(chats.items())
        emit({"bot": str(bot["username"]), "chats": [{"index": i, "name": name} for i, (_, name) in enumerate(options)]})
        selection = json.loads(sys.stdin.readline())
        index = selection.get("index")
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(options):
            emit({"error": "Selección cancelada o inválida; no se guardó ninguna configuración."})
            return 1
        chat_id = options[index][0]
        api(token, "sendMessage", {
            "chat_id": chat_id,
            "text": "Prueba de alertas TitoBot. El monitor aún no está activado.",
        })
        content = f"TELEGRAM_BOT_TOKEN={token}\nTELEGRAM_CHAT_ID={chat_id}\n".encode()
        fd = os.open(CONFIG, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            CONFIG.unlink(missing_ok=True)
            raise
        emit({"success": True, "message": "Mensaje de prueba aceptado por Telegram y configuración guardada. El monitor sigue detenido."})
        return 0
    except Exception as exc:
        # Never print exception text: HTTP errors can contain the secret URL.
        emit({"error": f"No se pudo completar la configuración ({type(exc).__name__})."})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
