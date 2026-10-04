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
    if "kraken_profit_vault" in engine.broker_config:
        del engine.broker_config["kraken_profit_vault"]
    if "kraken_initial_balance" in engine.broker_config:
        del engine.broker_config["kraken_initial_balance"]
    from config.broker_config import save_broker_config
    save_broker_config(engine.broker_config)
