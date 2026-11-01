#!/usr/bin/env python3
"""Independent, read-only monitor; never imports or controls the trading engine."""
import argparse
import json
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.error import URLError
from urllib.request import Request, urlopen


def load_state(path):
    if not path.exists():
        return {"initialized": False, "seen": [], "pending": [], "service": None}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("seen"), list) or not isinstance(data.get("pending"), list):
        raise ValueError("Invalid monitor state")
    return data


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".monitor-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def service_status():
    result = subprocess.run(
        ["systemctl", "is-active", "titobot.service"],
        capture_output=True, text=True, timeout=5, check=False,
    )
    status = result.stdout.strip()
    if status in {"active", "inactive", "failed", "activating", "deactivating", "reloading"}:
        return status
    return "desconocido"


def read_trades(path, max_age_seconds=120):
    age = time.time() - path.stat().st_mtime
    if age > max_age_seconds or age < -60:
        raise ValueError("History snapshot is stale or has an invalid timestamp")
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Invalid history")
    return [
        row for row in rows if isinstance(row, dict)
        and row.get("broker") == "IQOPTION"
        and row.get("category") == "BINARY_OPTIONS"
        and row.get("environment") == "PAPER"
        and row.get("settlement_verified") is True
        and row.get("id")
    ]


def daily_summary(rows, now):
    today = now.astimezone(ZoneInfo("America/Bogota")).date()
    seen = set()
    counts = {}
    total = Decimal("0")
    excluded = 0
    for row in rows:
        ident = str(row["id"])
        if ident in seen:
            continue
        seen.add(ident)
        try:
            closed = datetime.fromisoformat(row["closed_at"]).astimezone(ZoneInfo("America/Bogota"))
            pnl = Decimal(str(row["pnl"]))
            if not pnl.is_finite():
                raise ValueError("Invalid PnL")
        except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError):
            excluded += 1
            continue
        if closed.date() != today:
            continue
        result = str(row.get("result", "desconocido"))
        counts[result] = counts.get(result, 0) + 1
        total += pnl
    return (
        f"Resumen de binarias Demo del {today} (hora de Bogotá): "
        f"{sum(counts.values())} operaciones, resultados={counts}, PnL={total}. "
        f"Registros con fecha o PnL inválidos excluidos: {excluded}. "
        "Datos del historial del bot, sin verificación directa con IQ Option."
    )


def read_demo_balance(path, now=None, max_age_seconds=120):
    """Return only a fresh, explicitly identified practice-account reading."""
    if path is None:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("account") != "PRACTICE":
            return None
        observed = datetime.fromisoformat(data["observed_at"])
        if observed.tzinfo is None or observed.utcoffset() is None:
            return None
        current = now or datetime.now(timezone.utc)
        age = (current.astimezone(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds()
        if age < -5 or age > max_age_seconds:
            return None
        raw_amount = data["amount"]
        if isinstance(raw_amount, bool):
            return None
        amount = Decimal(str(raw_amount))
        currency = data["currency"]
        if not amount.is_finite() or amount < 0 or not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
            return None
        return {"amount": amount, "currency": currency, "observed_at": observed}
    except (OSError, ValueError, TypeError, KeyError, InvalidOperation, OverflowError):
        return None


def balance_line(balance):
    balance_text = "no disponible (sin lectura reciente verificada)"
    if balance is not None:
        observed = balance["observed_at"].astimezone(ZoneInfo("America/Bogota"))
        balance_text = (
            f'{balance["amount"]} {balance["currency"]} '
            f'(lectura {observed.strftime("%Y-%m-%d %H:%M:%S")} Bogotá)'
        )
    return f"💳 Saldo Demo (última lectura): {balance_text}"


def refresh_queued_balance(message, balance):
    """Refresh existing settlement alerts when actually sending them."""
    lines = message.splitlines()
    found = False
    for index, line in enumerate(lines):
        if line.startswith(("💳 Saldo Demo (última lectura):", "💳 Saldo Demo actual:")):
            lines[index] = balance_line(balance)
            found = True
    return "\n".join(lines) if found else message


def format_trade_alert(row, balance=None):
    """Present bot-reported Demo settlements without inventing account balances."""
    outcome = str(row.get("result") or "").strip().upper()
    if outcome in {"GANANCIA", "WIN", "WON"}:
        header = "🟢 GANANCIA"
    elif outcome in {"PÉRDIDA", "PERDIDA", "PÉRDIDA CONTROLADA", "PERDIDA CONTROLADA", "LOSS", "LOST"}:
        header = "🔴 PÉRDIDA"
    elif outcome in {"EMPATE", "DRAW", "TIE"}:
        header = "⚪ EMPATE"
    else:
        header = "⚠️ RESULTADO DESCONOCIDO"
    return (
        f"{header} · BINARIA DEMO\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 Activo: {row.get('symbol', '?')}\n"
        f"📈 Resultado registrado: {row.get('result', '?')}\n"
        f"💵 PnL: {row.get('pnl', '?')}\n"
        f"🕒 Cierre: {row.get('closed_at', '?')} (hora del servidor)\n"
        f"🔖 ID: {row.get('id', '?')}\n"
        f"{balance_line(balance)}\n\n"
        "ℹ️ Liquidación registrada por el bot; no comprobada directamente con IQ Option."
    )


def check_once(state, history, get_service=service_status, now=None, balance_path=None):
    """Only mutate the monitor's state; trade records are treated as unverified claims."""
    status = get_service()
    if state.get("service") is None or status != state["service"]:
        state["pending"].append(f"TitoBot: servicio {status}. Esto no confirma conexión con IQ Option.")
        state["service"] = status

    try:
        rows = read_trades(history)
    except (OSError, ValueError, TypeError):
        if not state.get("history_error"):
            state["pending"].append("TitoBot: historial inaccesible, inválido o desactualizado; no se conoce la actividad.")
        state["history_error"] = True
        return

    if state.get("history_error"):
        state["pending"].append("TitoBot: lectura del historial restablecida.")
        state["history_error"] = False

    ids = {str(row["id"]) for row in rows}
    if not state.get("initialized"):
        state["seen"] = sorted(ids)
        state["initialized"] = True
        state["pending"].append("Monitor iniciado. Historial previo tomado como referencia; sin verificación directa con IQ Option.")

    seen = set(state["seen"])
    added = set()
    for row in reversed(rows):
        ident = str(row["id"])
        if ident in seen or ident in added:
            continue
        added.add(ident)
        state["pending"].append(format_trade_alert(row))
    state["seen"] = sorted(seen | ids)
    current = (now or datetime.now(ZoneInfo("America/Bogota"))).astimezone(ZoneInfo("America/Bogota"))
    day = current.date().isoformat()
    if (current.hour, current.minute) >= (23, 55) and state.get("last_daily_report") != day:
        state["pending"].append(daily_summary(rows, current))
        state["last_daily_report"] = day


def send_message(token, chat_id, text):
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    with urlopen(request, timeout=10) as response:
        data = json.load(response)
        if response.status != 200 or data.get("ok") is not True:
            raise ValueError("Telegram rejected message")


def main():
    parser = argparse.ArgumentParser(description="Read-only TitoBot Telegram monitor")
    parser.add_argument("--history", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--balance", type=Path, help="Optional practice-balance snapshot")
    parser.add_argument("--interval", type=int, default=30)
    args = parser.parse_args()
    if args.interval < 10:
        parser.error("interval must be at least 10 seconds")
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        parser.error("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")
    if args.history.resolve() == args.state.resolve() or (
        args.balance and args.balance.resolve() == args.state.resolve()
    ):
        parser.error("state must be separate from input files")
    state = load_state(args.state)
    while True:
        try:
            check_once(state, args.history, balance_path=args.balance)
            save_state(args.state, state)
            while state["pending"]:
                message = refresh_queued_balance(
                    state["pending"][0], read_demo_balance(args.balance)
                )
                send_message(token, chat_id, message)
                state["pending"].pop(0)
                save_state(args.state, state)
        except (OSError, ValueError, TypeError, URLError, subprocess.SubprocessError) as exc:
            # Exception messages and URLs can contain the bot token.
            print("Monitor error:", type(exc).__name__, flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
