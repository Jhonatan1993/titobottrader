import json

import pytest

from trade_journal.journal import TradeJournal


def test_failed_replace_preserves_original_json(tmp_path, monkeypatch):
    path = tmp_path / "trades_history.json"
    original = [{"id": "old", "pnl": 1.0}]
    path.write_text(json.dumps(original), encoding="utf-8")
    journal = TradeJournal(storage_dir=str(tmp_path))

    def fail_replace(*args):
        raise OSError("simulated replace failure")

    monkeypatch.setattr("trade_journal.journal.os.replace", fail_replace)
    with pytest.raises(OSError):
        journal.record_trade({"id": "new", "pnl": -2.0}, strict=True)
    assert json.loads(path.read_text(encoding="utf-8")) == original
    assert list(tmp_path.glob(".trades-*")) == []


@pytest.mark.parametrize("contents", ["{invalid", '{"unexpected": "object"}'])
def test_invalid_history_fails_closed_without_overwriting(tmp_path, contents):
    path = tmp_path / "trades_history.json"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(RuntimeError):
        TradeJournal(storage_dir=str(tmp_path))
    assert path.read_text(encoding="utf-8") == contents


def test_successful_strict_write_can_be_reloaded(tmp_path):
    journal = TradeJournal(storage_dir=str(tmp_path))
    journal.record_trade({"id": "new", "pnl": -2.0}, strict=True)
    restored = TradeJournal(storage_dir=str(tmp_path))
    assert restored.trades[0]["id"] == "new"
    assert restored.trades[0]["pnl"] == -2.0
