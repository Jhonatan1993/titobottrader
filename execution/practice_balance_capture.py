"""Capture an opt-in, timestamped Practice balance without exposing credentials."""
import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path


def parse_practice_profile(profile, now=None):
    """Accept only one explicitly identified Practice balance with currency."""
    if not isinstance(profile, dict) or not isinstance(profile.get("balances"), list):
        return None
    matches = [
        entry for entry in profile["balances"]
        if isinstance(entry, dict) and type(entry.get("type")) is int and entry["type"] == 4
    ]
    if len(matches) != 1:
        return None
    try:
        entry = matches[0]
        raw = entry["amount"]
        if isinstance(raw, bool):
            return None
        amount = Decimal(str(raw))
        currency = entry["currency"]
        if not amount.is_finite() or amount < 0:
            return None
        if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
            return None
        observed = now or datetime.now(timezone.utc)
        if observed.tzinfo is None or observed.utcoffset() is None:
            return None
        return {
            "account": "PRACTICE",
            "amount": str(amount),
            "currency": currency,
            "observed_at": observed.astimezone(timezone.utc).isoformat(),
        }
    except (KeyError, InvalidOperation, ValueError, TypeError, OverflowError):
        return None


_write_lock = threading.Lock()


def _write_snapshot(path, snapshot):
    """Write on the auxiliary thread; always release the in-flight guard."""
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".practice-balance-", dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(snapshot, stream, ensure_ascii=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        return True
    except (OSError, ValueError, TypeError):
        return False
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            except OSError:
                pass
        _write_lock.release()


def capture_practice_balance(profile, destination=None, now=None):
    """Schedule at most one write without blocking the trading loop.

    A missing destination, invalid reading or busy worker drops the observation.
    Consumers must enforce freshness using the original observation time.
    """
    destination = destination or os.environ.get("IQOPTION_DEMO_BALANCE_CAPTURE_PATH")
    if not destination:
        return False
    snapshot = parse_practice_profile(profile, now=now)
    if snapshot is None or not _write_lock.acquire(blocking=False):
        return False
    try:
        threading.Thread(
            target=_write_snapshot, args=(Path(destination), snapshot), daemon=True
        ).start()
    except Exception:
        _write_lock.release()
        return False
    return True
