import copy
import pytest

from scripts.audit_risk_history import audit


def binary(ident, closed, pnl, environment="PAPER"):
    return {
        "id": f"BIN-{ident}",
        "broker": "IQOPTION",
        "environment": environment,
        "category": "BINARY_OPTIONS",
        "settlement_verified": True,
        "closed_at": closed,
        "pnl": pnl,
    }


def test_audit_reports_missing_ids_without_mutation():
    rows = [
        binary("1", "2026-11-01T01:00:00+00:00", 1.48),
        binary("2", "2026-11-01T02:00:00Z", -2.0),
        binary("3", "2026-11-01T02:00:00Z", 4.0, "LIVE_REAL"),
    ]
    state = {"date_utc": "2026-11-01", "realized_pnl": 1.48, "closed_trade_ids": ["1"]}
    original_rows, original_state = copy.deepcopy(rows), copy.deepcopy(state)
    result = audit(rows, state, "PAPER")
    assert result["matched_count"] == 1
    assert result["matched_pnl"] == 1.48
    assert result["missing_ids"] == ["2"]
    assert result["missing_pnl"] == -2.0
    assert rows == original_rows and state == original_state


def test_ambiguous_dates_and_duplicate_ids_are_excluded():
    rows = [
        binary("7", "2026-11-01 03:00:00", -2),
        binary("8", "2026-11-01T04:00:00Z", 1),
        binary("8", "2026-11-01T04:00:00Z", 1),
    ]
    state = {"date_utc": "2026-11-01", "realized_pnl": 0, "closed_trade_ids": []}
    result = audit(rows, state, "PAPER")
    assert result["invalid_rows_excluded"] == 1
    assert result["duplicate_ids_excluded"] == ["8"]
    assert result["missing_count"] == 0
    assumed = audit(rows, state, "PAPER", assume_naive_utc=True)
    assert assumed["missing_ids"] == ["7"]
    assert assumed["assumed_naive_utc"] is True


def test_invalid_risk_state_is_rejected():
    with pytest.raises(ValueError):
        audit([], {"date_utc": "2026-11-01", "realized_pnl": float("nan"),
                   "closed_trade_ids": []}, "PAPER")
