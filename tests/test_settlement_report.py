import pytest

from backtesting.settlement_report import analyze


def row(ident, opened, closed, pnl, stake=2.0, **changes):
    record = {
        "id": ident,
        "broker": "IQOPTION",
        "environment": "PAPER",
        "category": "BINARY_OPTIONS",
        "settlement_verified": True,
        "opened_at": opened,
        "closed_at": closed,
        "pnl": pnl,
        "invested_amount": stake,
    }
    record.update(changes)
    return record


def test_split_and_weighted_return():
    records = [
        row("1", "2026-01-01T10:00:00Z", "2026-01-01T10:01:00Z", 1.74),
        row("2", "2026-01-03T10:00:00Z", "2026-01-03T10:01:00Z", -2),
        row("3", "2026-01-03T11:00:00Z", "2026-01-03T11:01:00Z", 0),
    ]
    report = analyze(records, "2026-01-02T00:00:00Z", "PAPER")
    assert report["periods"]["before_cutoff"]["net_pnl"] == 1.74
    after = report["periods"]["on_or_after_cutoff"]
    assert after["trades"] == 2
    assert after["ties"] == 1
    assert after["return_per_unit_staked"] == -0.5
    assert report["excluded_rows"] == 0


def test_excludes_ambiguous_duplicates_and_crossing():
    good = row("1", "2026-01-01T10:00:00Z", "2026-01-01T10:01:00Z", -2)
    duplicate = dict(good)
    naive = row("2", "2026-01-01T10:00:00", "2026-01-01T10:01:00", 1)
    crossing = row("3", "2026-01-01T23:59:00Z", "2026-01-02T00:01:00Z", 1)
    invalid = row("4", "2026-01-03T10:00:00Z", "2026-01-03T10:01:00Z", float("nan"))
    unverified = row("5", "2026-01-03T10:00:00Z", "2026-01-03T10:01:00Z", 1,
                     settlement_verified=False)
    report = analyze([good, duplicate, naive, crossing, invalid, unverified],
                     "2026-01-02T00:00:00Z", "PAPER")
    assert report["excluded_rows"] == 6
    assert report["duplicate_ids_excluded"] == 1
    assert report["periods"]["before_cutoff"]["trades"] == 0
    assert report["periods"]["on_or_after_cutoff"]["trades"] == 0


def test_rejects_naive_cutoff_and_invalid_environment():
    with pytest.raises(ValueError):
        analyze([], "2026-01-02T00:00:00", "PAPER")
    with pytest.raises(ValueError):
        analyze([], "2026-01-02T00:00:00Z", "UNKNOWN")
