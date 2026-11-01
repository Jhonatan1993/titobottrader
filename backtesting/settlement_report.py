"""Offline descriptive report of bot-recorded binary settlements; not a backtest."""
import argparse
import datetime as dt
import json
import math


def parse_aware(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(dt.timezone.utc)


def summarize(items):
    wins = sum(pnl > 0 for pnl, stake in items)
    losses = sum(pnl < 0 for pnl, stake in items)
    ties = sum(pnl == 0 for pnl, stake in items)
    total_pnl = sum(pnl for pnl, stake in items)
    invested = sum(stake for pnl, stake in items)
    return {
        "trades": len(items), "wins": wins, "losses": losses, "ties": ties,
        "net_pnl": round(total_pnl, 4),
        "average_pnl_per_trade": round(total_pnl / len(items), 6) if items else None,
        "return_per_unit_staked": round(total_pnl / invested, 6) if invested else None,
        "decisive_win_rate": wins / (wins + losses) if wins + losses else None,
    }


def analyze(rows, cutoff, environment):
    """Split broker-labelled records by recorded closing time, without promoting parameters."""
    if environment not in {"PAPER", "LIVE_REAL"}:
        raise ValueError("explicit PAPER or LIVE_REAL environment required")
    cutoff = parse_aware(cutoff)
    if not isinstance(rows, list):
        raise ValueError("history must be a list")
    seen = set()
    duplicate = set()
    for row in rows:
        if isinstance(row, dict) and row.get("id"):
            key = (row.get("broker"), row.get("environment"), row.get("category"), str(row["id"]))
            if key in seen:
                duplicate.add(key)
            seen.add(key)

    periods = {"before_cutoff": [], "on_or_after_cutoff": []}
    excluded = 0
    for row in rows:
        try:
            if not isinstance(row, dict) or row.get("broker") != "IQOPTION":
                raise ValueError("invalid broker")
            if row.get("environment") != environment or row.get("category") != "BINARY_OPTIONS":
                raise ValueError("different environment or product")
            if row.get("settlement_verified") is not True or not row.get("id"):
                raise ValueError("unverified or missing id")
            key = (row["broker"], row["environment"], row["category"], str(row["id"]))
            if key in duplicate:
                raise ValueError("duplicate id")
            closed = parse_aware(row["closed_at"])
            opened = parse_aware(row["opened_at"])
            if opened > closed:
                raise ValueError("invalid ordering")
            pnl = float(row["pnl"])
            stake = float(row["invested_amount"])
            if not math.isfinite(pnl) or not math.isfinite(stake) or stake <= 0:
                raise ValueError("invalid monetary value")
            # Trades crossing the split may leak information across periods.
            if opened < cutoff <= closed:
                raise ValueError("trade crosses cutoff")
            period = "before_cutoff" if closed < cutoff else "on_or_after_cutoff"
            periods[period].append((pnl, stake))
        except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
            excluded += 1
    return {
        "kind": "descriptive_history_not_backtest",
        "environment": environment,
        "cutoff_utc": cutoff.isoformat(),
        "excluded_rows": excluded,
        "duplicate_ids_excluded": len(duplicate),
        "source_caveat": "Bot-reported settlement flag; not independently reconciled with broker.",
        "periods": {name: summarize(values) for name, values in periods.items()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history", help="Path to history JSON (read only)")
    parser.add_argument("--cutoff", required=True, help="ISO 8601 split with timezone")
    parser.add_argument("--environment", required=True, choices=["PAPER", "LIVE_REAL"])
    args = parser.parse_args()
    with open(args.history, encoding="utf-8") as stream:
        rows = json.load(stream)
    print(json.dumps(analyze(rows, args.cutoff, args.environment), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
