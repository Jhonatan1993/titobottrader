import os
import json
from typing import Dict, Any

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "broker_config.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "operating_mode": "IQ_CFD",       # Modo predeterminado
    "active_broker": "IQOPTION",      # Broker único exclusivo
    "iq_mode": "FOREX_CFD",
    "iqoption_environment": "PAPER",  # PAPER por defecto; LIVE_REAL requiere armado explícito
    "iqoption_paper_initial_balance": 10000.0,
    "iqoption_initial_balance": 10000.0,
    "iqoption_profit_target_amount": 50000.0,
    "iqoption_profit_target_enabled": True,
    "iqoption_max_loss_amount": 0.0,
    "iqoption_max_loss_enabled": True,
    "profit_target_amount": 50000.0,
    "profit_target_enabled": True,
    "max_loss_amount": 0.0,
    "max_loss_enabled": True,
    "iqoption": {
        "email": os.environ.get("IQOPTION_EMAIL", ""),
        "password": os.environ.get("IQOPTION_PASSWORD", ""),
        "ssid": os.environ.get("IQOPTION_SSID", ""),
        "enabled": False
    }
}


def live_trading_armed() -> bool:
    """Real trading requires an explicit process-level release flag; JSON/UI cannot arm it."""
    return os.environ.get("LIVE_TRADING_ARMED", "false").strip().lower() == "true"


def live_cfd_execution_verified() -> bool:
    """Separate release gate for CFD contract sizing against the requested account risk."""
    return os.environ.get("LIVE_CFD_EXECUTION_VERIFIED", "false").strip().lower() == "true"


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
