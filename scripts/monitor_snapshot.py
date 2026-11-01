#!/usr/bin/env python3
"""Publish a minimal, atomic snapshot of bot-reported demo binary settlements."""
import argparse
import json
import os
import tempfile
from pathlib import Path

FIELDS = (
    "id", "broker", "category", "environment", "settlement_verified",
    "symbol", "result", "pnl", "closed_at",
)


def make_snapshot(source, destination):
    source = Path(source)
    destination = Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError("Source and destination must differ")
    rows = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("History must be a list")
    selected = [
        {key: row[key] for key in FIELDS if key in row}
        for row in rows
        if isinstance(row, dict)
        and row.get("broker") == "IQOPTION"
        and row.get("category") == "BINARY_OPTIONS"
        and row.get("environment") == "PAPER"
        and row.get("settlement_verified") is True
        and row.get("id")
    ]
    fd, temp = tempfile.mkstemp(prefix=".snapshot-", dir=str(destination.parent))
    try:
        os.fchmod(fd, 0o640)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(selected, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, destination)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    make_snapshot(args.source, args.destination)


if __name__ == "__main__":
    main()
