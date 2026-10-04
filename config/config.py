from dataclasses import dataclass
import os

@dataclass(frozen=True)
class AppConfig:
    # Default to PAPER for MVP live/paper evaluation. BACKTEST remains available via env var.
    APP_MODE: str = os.getenv("APP_MODE", "PAPER")
    SYMBOL: str = os.getenv("SYMBOL", "BTCUSDT")
    TIMEFRAME: str = os.getenv("TIMEFRAME", "15m")
    INITIAL_BALANCE: float = float(os.getenv("INITIAL_BALANCE", "10000"))
    RISK_PER_TRADE: float = float(os.getenv("RISK_PER_TRADE", "0.005"))
    MAX_DAILY_LOSS: float = float(os.getenv("MAX_DAILY_LOSS", "0.02"))
    MAX_OPEN_TRADES: int = int(os.getenv("MAX_OPEN_TRADES", "3"))
    MIN_RISK_REWARD: float = float(os.getenv("MIN_RISK_REWARD", "1.5"))
    AI_ENABLED: bool = os.getenv("AI_ENABLED", "true").lower() == "true"
    LIVE_TRADING: bool = os.getenv("LIVE_TRADING", "false").lower() == "true"

    def validate(self) -> None:
        if self.LIVE_TRADING:
            raise ValueError("LIVE_TRADING must remain FALSE in MVP mode.")
        if self.APP_MODE.upper() not in {"BACKTEST", "PAPER"}:
            raise ValueError("APP_MODE must be BACKTEST or PAPER.")
        if self.RISK_PER_TRADE <= 0 or self.RISK_PER_TRADE > 1:
            raise ValueError("RISK_PER_TRADE must be between 0 and 1.")
        if self.MAX_DAILY_LOSS <= 0 or self.MAX_DAILY_LOSS > 1:
            raise ValueError("MAX_DAILY_LOSS must be between 0 and 1.")
        if self.MAX_OPEN_TRADES < 1:
            raise ValueError("MAX_OPEN_TRADES must be at least 1.")

config = AppConfig()
config.validate()
