from risk_management.iqoption_risk_policy import IQOptionRiskPolicy


def test_allows_only_one_global_position():
    policy = IQOptionRiskPolicy(
        profit_target_amount=100.0,
        max_loss_amount=50.0,
    )

    assert policy.can_open(active_positions=0).allowed is True

    decision = policy.can_open(active_positions=1)
    assert decision.allowed is False
    assert decision.reason == "MAXIMO_GLOBAL_DE_UNA_POSICION"


def test_blocks_openings_while_order_is_pending():
    policy = IQOptionRiskPolicy()

    decision = policy.can_open(active_positions=0, pending_order=True)

    assert decision.allowed is False
    assert decision.reason == "ORDEN_EN_TRANSITO"


def test_halts_after_daily_profit_target():
    policy = IQOptionRiskPolicy(
        profit_target_amount=25.0,
        max_loss_amount=50.0,
        profit_target_enabled=True,
    )

    policy.record_closed_trade(25.0)
    decision = policy.can_open(active_positions=0)

    assert decision.allowed is False
    assert decision.reason == "META_DIARIA_ALCANZADA"
    assert policy.snapshot()["halted"] is True


def test_halts_after_daily_loss_limit():
    policy = IQOptionRiskPolicy(
        profit_target_amount=100.0,
        max_loss_amount=20.0,
        max_loss_enabled=True,
    )

    policy.record_closed_trade(-20.0)
    decision = policy.can_open(active_positions=0)

    assert decision.allowed is False
    assert decision.reason == "LIMITE_PERDIDA_DIARIA_ALCANZADO"
    assert policy.snapshot()["realized_pnl"] == -20.0


def test_disabled_limits_do_not_block_entries():
    policy = IQOptionRiskPolicy(
        profit_target_amount=1.0,
        max_loss_amount=1.0,
        profit_target_enabled=False,
        max_loss_enabled=False,
    )

    policy.record_closed_trade(100.0)
    policy.record_closed_trade(-200.0)

    assert policy.can_open(active_positions=0).allowed is True
