from types import SimpleNamespace
from unittest.mock import Mock

from execution.trading_engine import RealTimeTradingEngine
from risk_management.iqoption_risk_policy import IQOptionRiskPolicy
from telegram_service.telegram_bot import TelegramService


def test_pause_during_pending_order_and_resume_blocked(tmp_path):
    policy = IQOptionRiskPolicy(state_path=str(tmp_path / "risk.json"))
    assert policy.begin_binary_order()
    engine = RealTimeTradingEngine.__new__(RealTimeTradingEngine)
    engine.iqoption_risk_policy = policy
    engine.active_broker = "IQOPTION"
    engine.broker_wallets = {"IQOPTION": {"is_running": True}}
    engine.open_positions = {}
    engine.is_running = True
    engine.agent = SimpleNamespace(_add_thought=Mock())
    assert engine.toggle_pause() is False
    assert engine.broker_wallets["IQOPTION"]["is_running"] is False
    assert engine.toggle_pause() is False
    assert policy.snapshot()["binary_order_pending"] is True
    assert not policy.snapshot()["reconciliation_required"]


def test_daily_loss_blocks_resume():
    policy = IQOptionRiskPolicy(max_loss_amount=2, max_loss_enabled=True)
    policy.record_closed_trade(-2, trade_id="1")
    engine = RealTimeTradingEngine.__new__(RealTimeTradingEngine)
    engine.iqoption_risk_policy = policy
    engine.active_broker = "IQOPTION"
    engine.broker_wallets = {"IQOPTION": {"is_running": False}}
    engine.open_positions = {}
    engine.is_running = False
    assert engine.resume_trading() is False
    assert engine.broker_wallets["IQOPTION"]["is_running"] is False
    assert policy.snapshot()["realized_pnl"] == -2


def test_telegram_delegates_controls_and_never_resets_risk():
    service = TelegramService.__new__(TelegramService)
    service.send_message = Mock()
    service.engine = SimpleNamespace(
        pause_trading=Mock(),
        resume_trading=Mock(return_value=False),
        binary_engine=SimpleNamespace(soros_manager=SimpleNamespace(manual_reset=Mock())),
    )
    service._handle_command("/pause")
    service._handle_command("/resume")
    assert "BLOQUEADA" in service.send_message.call_args.args[0]
    service._handle_command("/reset")
    service._handle_command("/stop")
    assert service.engine.pause_trading.call_count == 2
    service.engine.resume_trading.assert_called_once()
    service.engine.binary_engine.soros_manager.manual_reset.assert_not_called()
    assert "no se cierran automáticamente" in service.send_message.call_args.args[0]
