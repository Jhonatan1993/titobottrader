#!/usr/bin/env python3
"""Compare bot-reported binary settlements with a risk snapshot, without writes."""
import argparse
import datetime as dt
import json
import math


def audit(rows, state, environment, assume_naive_utc=False):
    if not isinstance(rows, list) or not isinstance(state, dict):
        raise ValueError("history must be a list and state must be an object")
    if environment not in {"PAPER", "LIVE_REAL"}:
        raise ValueError("explicit environment required")
    day = dt.date.fromisoformat(state["date_utc"])
    raw_ids = state.get("closed_trade_ids")
    if not isinstance(raw_ids, list) or any(not isinstance(x, str) or not x for x in raw_ids):
        raise ValueError("invalid risk ids")
    risk_ids = set(raw_ids)
    if len(risk_ids) != len(raw_ids):
        raise ValueError("duplicate risk ids")
    risk_pnl = float(state["realized_pnl"])
    if not math.isfinite(risk_pnl):
        raise ValueError("invalid risk PnL")
    unique, duplicates = {}, set()
    excluded = 0
    for row in rows:
        if not isinstance(row, dict):
            excluded += 1
            continue
        if (row.get("broker") != "IQOPTION" or row.get("environment") != environment
                or row.get("category") != "BINARY_OPTIONS" or row.get("settlement_verified") is not True):
            continue
        try:
            ident = str(row["id"])
            if not ident.startswith("BIN-") or not ident[4:].isdigit():
                raise ValueError("unrecognized id")
            ident = ident[4:]
            when = dt.datetime.fromisoformat(row["closed_at"].replace("Z", "+00:00"))
            if when.tzinfo is None or when.utcoffset() is None:
                if not assume_naive_utc:
                    raise ValueError("timestamp without timezone")
                when = when.replace(tzinfo=dt.timezone.utc)
            if when.astimezone(dt.timezone.utc).date() != day:
                continue
            pnl = float(row["pnl"])
            if not math.isfinite(pnl):
                raise ValueError("invalid PnL")
            if ident in unique:
                duplicates.add(ident)
            else:
                unique[ident] = pnl
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            excluded += 1
    for ident in duplicates:
        unique.pop(ident, None)
    matched = set(unique) & risk_ids
    missing = set(unique) - risk_ids
    return {
        "date_utc": day.isoformat(),
        "environment": environment,
        "assumed_naive_utc": assume_naive_utc,
        "risk_realized_pnl": risk_pnl,
        "matched_count": len(matched),
        "matched_pnl": round(sum(unique[i] for i in matched), 2),
        "missing_count": len(missing),
        "missing_pnl": round(sum(unique[i] for i in missing), 2),
        "missing_ids": sorted(missing),
        "risk_ids_not_in_selected_history": sorted(risk_ids - set(unique)),
        "duplicate_ids_excluded": sorted(duplicates),
        "invalid_rows_excluded": excluded,
        "caveat": "Internal records only; risk state is not scoped by account or product and broker settlement was not independently checked.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history")
    parser.add_argument("risk_state")
    parser.add_argument("--environment", required=True, choices=["PAPER", "LIVE_REAL"])
    parser.add_argument("--assume-naive-utc", action="store_true")
    args = parser.parse_args()
    with open(args.history, encoding="utf-8") as stream:
        rows = json.load(stream)
    with open(args.risk_state, encoding="utf-8") as stream:
        state = json.load(stream)
    print(json.dumps(audit(rows, state, args.environment, args.assume_naive_utc), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
