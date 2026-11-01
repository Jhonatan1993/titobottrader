#!/usr/bin/env python3
"""Obtain a fresh IQ Option practice balance without submitting orders."""
import argparse
import json
import os
import re
import ssl
import tempfile
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import websocket


class BalanceReadError(ValueError):
    """A fixed, non-sensitive reason for a failed balance read."""


def parse_demo_profile(data):
    if not isinstance(data, dict) or data.get("name") != "profile":
        return None
    profile = data.get("msg")
    if not isinstance(profile, dict) or not isinstance(profile.get("balances"), list):
        return None
    matches = [b for b in profile["balances"] if isinstance(b, dict) and type(b.get("type")) is int and b["type"] == 4]
    if len(matches) != 1:
        return None
    entry = matches[0]
    try:
        raw = entry["amount"]
        if isinstance(raw, bool):
            return None
        amount = Decimal(str(raw))
        currency = entry["currency"]
        if not amount.is_finite() or amount < 0 or not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
            return None
    except (KeyError, InvalidOperation, ValueError):
        return None
    return {"account": "PRACTICE", "amount": str(amount), "currency": currency}


def query_demo_balance(ssid, *, connect=websocket.create_connection, timeout=12):
    if not isinstance(ssid, str) or not ssid.strip() or "\n" in ssid or "\r" in ssid:
        raise ValueError("Sesión no disponible")
    ssid = ssid.strip()
    ws = connect(
        "wss://ws.iqoption.com/echo/websocket",
        header=["Origin: https://iqoption.com", "User-Agent: Mozilla/5.0", "Cookie: ssid=" + ssid],
        timeout=5, sslopt={"cert_reqs": ssl.CERT_REQUIRED, "check_hostname": True},
    )
    try:
        ws.send(json.dumps({"name": "authenticate", "msg": {"ssid": ssid, "protocol": 3, "session_id": "", "client_session_id": ""}, "request_id": "readonly_demo_balance"}))
        ws.send(json.dumps({"name": "ssid", "msg": ssid}))
        deadline = time.monotonic() + timeout
        saw_profile = False
        while time.monotonic() < deadline:
            try:
                frame = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            if not frame:
                break
            try:
                data = json.loads(frame)
                if isinstance(data, dict) and data.get("name") == "profile":
                    saw_profile = True
                profile = parse_demo_profile(data)
            except (ValueError, TypeError):
                continue
            if profile is not None:
                profile["observed_at"] = datetime.now(timezone.utc).isoformat()
                return profile
        if saw_profile:
            raise BalanceReadError("PERFIL_SIN_SALDO_DEMO_VALIDO")
        raise BalanceReadError("PERFIL_NO_RECIBIDO")
    finally:
        ws.close()


def query_with_retry(ssid, *, query=query_demo_balance, sleep=time.sleep):
    """Retry one missing-profile response; never reuse a previous balance."""
    for attempt in range(2):
        try:
            return query(ssid, timeout=8)
        except BalanceReadError as exc:
            if attempt == 1 or str(exc) != "PERFIL_NO_RECIBIDO":
                raise
            sleep(1)


def publish_snapshot(destination, snapshot):
    destination = Path(destination)
    fd, temporary = tempfile.mkstemp(prefix=".demo-balance-", dir=str(destination.parent))
    try:
        os.fchmod(fd, 0o640)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(snapshot, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    if args.config.resolve() == args.destination.resolve():
        parser.error("El destino debe ser distinto a la configuración")
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        ssid = config.get("iqoption", {}).get("ssid")
        snapshot = query_with_retry(ssid, query=query_demo_balance)
        publish_snapshot(args.destination, snapshot)
        print("Lectura Demo actualizada; importe y credenciales omitidos.")
        return 0
    except Exception as exc:
        # Invalidate the previous reading immediately; never publish credentials.
        try:
            publish_snapshot(args.destination, {
                "account": "PRACTICE",
                "status": "unavailable",
                "observed_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            # The existing reading may remain on disk; consumers must enforce
            # its original observation time and a strict maximum age.
            print("No se pudo invalidar la instantánea anterior.")
        # Do not log exception text: it can contain session credentials.
        allowed = {"PERFIL_NO_RECIBIDO", "PERFIL_SIN_SALDO_DEMO_VALIDO"}
        reason = str(exc) if isinstance(exc, BalanceReadError) and str(exc) in allowed else type(exc).__name__
        print("No se pudo actualizar el saldo Demo:", reason)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
