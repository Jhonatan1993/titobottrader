import pytest
from execution.trading_engine import RealTimeTradingEngine

def test_financial_symmetry_binance_and_alpaca():
    """
    Verifica que la matemática financiera de Bóveda, Base y Capital Total (NAV)
    sea 100% idéntica y simétrica entre Binance y Alpaca.
    """
    engine = RealTimeTradingEngine(execution_environment="PAPER")
    
    # 1. Binance State Check
    engine.set_active_broker("BINANCE")
    bin_state = engine.get_state()
    bin_fin = bin_state["financial_summary"]
    
    assert "total_equity" in bin_fin
    assert "cash_available" in bin_fin
    assert "operating_capital_base" in bin_fin
    assert "profit_vault" in bin_fin
    
    # Fórmula canónica: Total Equity = Base + Profit_Vault
    expected_bin_equity = round(bin_fin["operating_capital_base"] + bin_fin["profit_vault"], 2)
    assert bin_fin["total_equity"] == expected_bin_equity
    
    # Total profit = Profit_Vault
    assert bin_fin["total_profit_usd"] == round(bin_fin["profit_vault"], 2)

    # 2. Alpaca State Check
    engine.set_active_broker("ALPACA")
    alp_state = engine.get_state()
    alp_fin = alp_state["financial_summary"]
    
    assert "total_equity" in alp_fin
    assert "cash_available" in alp_fin
    assert "operating_capital_base" in alp_fin
    assert "profit_vault" in alp_fin
    
    expected_alp_equity = round(alp_fin["operating_capital_base"] + alp_fin["profit_vault"], 2)
    assert alp_fin["total_equity"] == expected_alp_equity
    
    assert alp_fin["total_profit_usd"] == round(alp_fin["profit_vault"], 2)

def test_new_broker_creation_and_symmetry():
    """
    Verifica que si se agrega un nuevo broker (ej. KRAKEN), el motor financiero
    funciona exactamente igual sin requerir cambios de código específicos.
    """
    engine = RealTimeTradingEngine(execution_environment="PAPER")
    
    # Limpiar cualquier clave residual de pruebas anteriores
    for k in ["kraken_profit_vault", "kraken_paper_profit_vault", "kraken_initial_balance"]:
        engine.broker_config.pop(k, None)
    
    # Registrar nuevo broker dinámicamente
    engine.broker_wallets["KRAKEN"] = {
        "id": "KRAKEN",
        "name": "Kraken Exchange",
        "icon": "🐙",
        "category": "CRYPTO",
        "allowed_categories": ["CRYPTO"],
        "environment": "PAPER",
        "initial_balance": 100.0,
        "cash": 100.0,
        "profit_vault": 15.0,
        "target_amount": 500.0,
        "max_loss_amount": 20.0,
        "target_reached": False,
        "loss_limit_reached": False,
        "is_running": True
    }
    
    # 1. Cambiar al nuevo broker
    res = engine.set_active_broker("KRAKEN")
    assert res["success"] is True
    assert engine.active_broker == "KRAKEN"
    
    # 2. Consultar equity y estado
    kr_equity = engine.get_broker_equity("KRAKEN")
    # Base 100 + Bóveda 15 = 115.00
    assert kr_equity == 115.0
    
    state = engine.get_state()
    assert "KRAKEN" in state["system_status"]["brokers"]
    kr_info = state["system_status"]["brokers"]["KRAKEN"]
    assert kr_info["initial_balance"] == 100.0
    assert kr_info["cash"] == 100.0
    assert kr_info["profit_vault"] == 15.0
    assert kr_info["equity"] == 115.0
    
    # 3. Transferir de la Bóveda al Capital en el nuevo broker
    transfer_res = engine.transfer_vault_to_capital("KRAKEN", 10.0)
    assert transfer_res["success"] is True
    assert transfer_res["transferred_amount"] == 10.0
    assert transfer_res["new_initial_balance"] == 110.0
    assert transfer_res["new_cash"] == 110.0
    assert transfer_res["remaining_vault"] == 5.0
    
    # El Capital Total (NAV) sigue siendo exactamente 115.00 (conservación de capital)
    assert engine.get_broker_equity("KRAKEN") == 115.0

    # Limpieza: restaurar BINANCE como broker activo
    engine.set_active_broker("BINANCE")
    for k in ["kraken_profit_vault", "kraken_paper_profit_vault", "kraken_initial_balance"]:
        engine.broker_config.pop(k, None)
    from config.broker_config import save_broker_config
    save_broker_config(engine.broker_config)

def test_binance_live_real_vault_preservation_and_exact_sync():
    """
    Verifica que en MODO REAL de Binance:
    1. Las sincronizaciones continuas de Binance NO destruyan ni reseteen la Bóveda de Ganancias a 0.0.
    2. El Capital Base Operativo se calcule correctamente como: Total Equity - Bóveda.
    3. Total Equity sea exactamente igual al saldo real reportado por Binance (ej. 14.87 USD).
    4. La Bóveda de Ganancias (ej. 0.11 USD) permanezca blindada e intocable.
    """
    engine = RealTimeTradingEngine(execution_environment="PAPER")
    engine.set_active_broker("BINANCE")
    engine.broker_wallets["BINANCE"]["environment"] = "LIVE_REAL"
    engine.broker_wallets["BINANCE"]["profit_vault"] = 0.11
    engine.broker_config["binance_profit_vault"] = 0.11

    # Simular datos reales de Binance (como los del usuario: 14.87 USD total en Binance, 13.91 USDT disponible)
    acc_data = {
        "authenticated": True,
        "can_trade": True,
        "usdt_free": 13.91,
        "total_stable_free": 13.91,
        "total_spot_equity": 14.87,
        "balances": {
            "USDT": {"free": 13.91, "locked": 0.0, "total": 13.91},
            "BTC": {"free": 0.00001, "locked": 0.0, "total": 0.00001}
        }
    }

    # Ejecutar sincronización (la que antes reseteaba la bóveda a 0.0 cada 3 segundos)
    engine._sync_binance_wallet_positions(acc_data)

    # 1. La Bóveda DEBE mantenerse intacta en 0.11 USD
    assert engine.broker_wallets["BINANCE"]["profit_vault"] == 0.11
    assert engine.broker_config["binance_profit_vault"] == 0.11

    # 2. El Capital Base debe ser exactamente: 14.87 - 0.11 = 14.76 USD
    assert engine.broker_wallets["BINANCE"]["initial_balance"] == 14.76
    assert engine.initial_balance == 14.76

    # 3. El Capital Total (NAV) debe ser 14.87 USD
    assert engine.get_broker_equity("BINANCE") == 14.87

    # 4. Estado financiero exportado a la interfaz
    state = engine.get_state()
    fin = state["financial_summary"]
    assert fin["total_equity"] == 14.87
    assert fin["operating_capital_base"] == 14.76
    assert fin["profit_vault"] == 0.11
    # Base + Bóveda = Total Equity
    assert round(fin["operating_capital_base"] + fin["profit_vault"], 2) == fin["total_equity"]

    # 5. Probar transferencia de la Bóveda al Capital Base
    res = engine.transfer_vault_to_capital("BINANCE", 0.11)
    assert res["success"] is True
    assert res["remaining_vault"] == 0.0
    assert res["new_initial_balance"] == 14.87
    assert engine.get_broker_equity("BINANCE") == 14.87


def test_iqoption_vault_and_trade_isolation_between_paper_and_real():
    """
    Verifica que la Bóveda de Ganancias y las estadísticas de operaciones estén
    estrictamente aisladas entre MODO PAPER y MODO REAL para IQ Option.
    Las ganancias y operaciones del modo simulación jamás deben contaminar la cuenta real.
    """
    engine = RealTimeTradingEngine(execution_environment="PAPER")
    engine.set_active_broker("IQOPTION")
    
    # 1. En Modo Paper: Simular ganancia en bóveda y registrar operaciones de prueba
    engine.save_broker_vault("IQOPTION", 12.14, env="PAPER")
    engine.journal.record_trade({
        "symbol": "EURUSD",
        "broker": "IQOPTION",
        "environment": "PAPER",
        "pnl": 12.14,
        "invested_amount": 50.0,
        "exit_price": 1.0950,
        "entry_price": 1.0900
    })

    # Verificar estado en PAPER
    paper_state = engine.get_state()
    assert paper_state["system_status"]["execution_environment"] == "PAPER"
    assert paper_state["financial_summary"]["profit_vault"] == 12.14
    assert paper_state["financial_summary"]["winning_trades_count"] >= 1

    # 2. Conmutar a MODO REAL
    # Simular que IQ Option se activa en LIVE_REAL con saldo real de 0.00 USD
    engine.broker_wallets["IQOPTION"]["environment"] = "LIVE_REAL"
    engine.broker_wallets["IQOPTION"]["cash"] = 0.0
    engine.broker_wallets["IQOPTION"]["initial_balance"] = 0.0
    engine.broker_wallets["IQOPTION"]["profit_vault"] = engine.get_broker_vault("IQOPTION", "LIVE_REAL")
    engine.execution_environment = "LIVE_REAL"

    # Verificar estado en LIVE_REAL
    real_state = engine.get_state()
    assert real_state["system_status"]["execution_environment"] == "LIVE_REAL"
    
    # La Bóveda REAL DEBE estar en 0.00 USD (no contaminada con los 12.14 de paper)
    assert real_state["financial_summary"]["profit_vault"] == 0.0
    assert real_state["financial_summary"]["total_profit_usd"] == 0.0
    assert real_state["system_status"]["brokers"]["IQOPTION"]["profit_vault"] == 0.0

    # Las estadísticas de trades en LIVE_REAL deben mostrar 0 trades reales
    assert real_state["financial_summary"]["total_trades_count"] == 0
    assert real_state["financial_summary"]["win_rate"] == 0.0
    assert len(real_state["completed_trades"]) == 0

    # 3. Conmutar de vuelta a PAPER
    engine.broker_wallets["IQOPTION"]["environment"] = "PAPER"
    engine.broker_wallets["IQOPTION"]["profit_vault"] = engine.get_broker_vault("IQOPTION", "PAPER")
    engine.execution_environment = "PAPER"

    restored_state = engine.get_state()
    assert restored_state["financial_summary"]["profit_vault"] == 12.14
    assert restored_state["financial_summary"]["total_trades_count"] >= 1

