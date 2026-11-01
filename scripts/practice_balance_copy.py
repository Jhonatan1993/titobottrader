#!/usr/bin/env python3
"""Copy a fresh, minimal Practice balance without exposing broker credentials."""
import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path


def validated_reading(source, now=None, max_age=120):
    try:
        data = json.loads(Path(source).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("account") != "PRACTICE":
            return None
        observed = datetime.fromisoformat(data["observed_at"])
        if observed.tzinfo is None or observed.utcoffset() is None:
            return None
        current = now or datetime.now(timezone.utc)
        age = (current.astimezone(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds()
        raw = data["amount"]
        if isinstance(raw, bool) or not -5 <= age <= max_age:
            return None
        amount = Decimal(str(raw))
        currency = data["currency"]
        if not amount.is_finite() or amount < 0 or not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
            return None
        return {
            "account": "PRACTICE",
            "amount": str(amount),
            "currency": currency,
            "observed_at": observed.astimezone(timezone.utc).isoformat(),
        }
    except (OSError, ValueError, TypeError, KeyError, InvalidOperation, OverflowError):
        return None


def publish_copy(source, destination, now=None):
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError("source and destination must differ")
    reading = validated_reading(source, now=now)
    data = reading if reading is not None else {"account": "PRACTICE", "status": "unavailable"}
    fd, temporary = tempfile.mkstemp(prefix=".practice-copy-", dir=str(destination.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o640)
            json.dump(data, stream, ensure_ascii=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return reading is not None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        available = publish_copy(args.source, args.destination)
    except (OSError, ValueError, TypeError):
        print("No se pudo publicar la lectura Demo.")
        return 1
    print("Lectura Demo copiada." if available else "Lectura Demo no disponible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
