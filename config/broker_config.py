import os
import json
from typing import Dict, Any

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "broker_config.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "operating_mode": "BINANCE_CRYPTO",  # "SIMULATION", "ALPACA_PAPER", "BINANCE_CRYPTO", "HYBRID"
    "active_broker": "BINANCE",  # "BINANCE", "ALPACA"
    "profit_target_amount": 500.0,
    "profit_target_enabled": True,
    "max_loss_amount": 150.0,
    "max_loss_enabled": True,
    "paper_initial_balance": 30.0,
    "alpaca_initial_balance": 100000.0,
    "binance_profit_vault": 0.0,
    "alpaca_profit_vault": 0.0,
    "alpaca": {
        "api_key": os.environ.get("ALPACA_API_KEY", ""),
        "secret_key": os.environ.get("ALPACA_SECRET_KEY", ""),
        "base_url": os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"),
        "data_url": "https://data.alpaca.markets/v2",
        "enabled": False
    },
    "binance": {
        "api_key": os.environ.get("BINANCE_API_KEY", ""),
        "secret_key": os.environ.get("BINANCE_SECRET_KEY", ""),
        "testnet": False,
        "live_trading_enabled": False,
        "base_url": "https://api.binance.com/api/v3",
        "public_url": "https://api.binance.com/api/v3",
        "enabled": True
    },
    "iqoption_initial_balance": 10000.0,
    "iqoption_profit_vault": 0.0,
    "iqoption_environment": "PAPER",
    "iqoption": {
        "email": os.environ.get("IQOPTION_EMAIL", ""),
        "password": os.environ.get("IQOPTION_PASSWORD", ""),
        "ssid": os.environ.get("IQOPTION_SSID", ""),
        "enabled": False
    }
}

def load_broker_config() -> Dict[str, Any]:
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                config = DEFAULT_CONFIG.copy()
                config.update(data)
                return config
        except Exception:
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()

def save_broker_config(config: Dict[str, Any]) -> bool:
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        if os.name == 'posix':
            try:
                os.chmod(CONFIG_FILE, 0o600)
            except Exception:
                pass
        return True
    except Exception:
        return False
