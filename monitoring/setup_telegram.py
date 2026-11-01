#!/usr/bin/env python3
"""Interactive Telegram setup; the token is never printed or placed on a command line."""
import getpass
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
        raise ValueError("Telegram rejected request")
    return result.get("result")


def main():
    if os.geteuid() != 0:
        print("Ejecuta esta configuración como administrador en la VPS.")
        return 1
    if not sys.stdin.isatty():
        print("Se necesita una terminal interactiva.")
        return 1
    if CONFIG.exists() or CONFIG.is_symlink():
        print("La configuración ya existe; no se sobrescribirá.")
        return 1
    token = getpass.getpass("Token de BotFather (no se mostrará): ").strip()
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token):
        print("Formato de token no válido. No se guardó ninguna configuración.")
        return 1
    try:
        webhook = api(token, "getWebhookInfo")
        if not isinstance(webhook, dict) or webhook.get("url"):
            print("El bot usa un webhook o no se pudo verificar; no se modificó.")
            return 1
        updates = api(token, "getUpdates", {"limit": 100, "timeout": 0})
        if not isinstance(updates, list):
            raise ValueError("Unexpected response")
        chats = {}
        for update in updates:
            message = update.get("message", {}) if isinstance(update, dict) else {}
            chat = message.get("chat", {}) if isinstance(message, dict) else {}
            if not isinstance(chat, dict) or chat.get("type") != "private":
                continue
            if not str(message.get("text", "")).startswith("/start"):
                continue
            ident = chat.get("id")
            if not isinstance(ident, int) or isinstance(ident, bool) or ident <= 0:
                continue
            label = str(chat.get("first_name", "Chat privado")).replace("\n", " ")[:60]
            chats[ident] = label
        if not chats:
            print("No se encontró un chat privado con /start. Envíalo al bot e inténtalo de nuevo.")
            return 1
        options = list(chats.items())
        for index, (_, label) in enumerate(options, 1):
            print(f"{index}. {label}")
        choice = input("Número del chat que recibirá las alertas: ").strip()
        if not choice.isdigit() or not 1 <= int(choice) <= len(options):
            print("Selección inválida; no se guardó ninguna configuración.")
            return 1
        chat_id = options[int(choice) - 1][0]
        if input("¿Enviar un mensaje de prueba a ese chat? [s/N]: ").strip().lower() != "s":
            print("Cancelado; no se guardó ninguna configuración.")
            return 1
        api(token, "sendMessage", {
            "chat_id": chat_id,
            "text": "Prueba de alertas TitoBot. El monitor aún no está activado.",
        })
    except Exception as exc:
        # Error messages can contain the token in the request URL.
        print("No se pudo verificar o enviar la prueba:", type(exc).__name__)
        return 1

    content = f"TELEGRAM_BOT_TOKEN={token}\nTELEGRAM_CHAT_ID={chat_id}\n".encode("utf-8")
    try:
        fd = os.open(CONFIG, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        print("La prueba se envió, pero no se pudo guardar la configuración:", type(exc).__name__)
        return 1
    print("Configuración guardada con permisos privados. El monitor aún no está iniciado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
