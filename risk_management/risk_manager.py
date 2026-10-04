from typing import Dict

class RiskManager:
    def __init__(self, initial_balance: float, risk_per_trade: float, max_daily_loss: float, max_open_trades: int):
        self.initial_balance = initial_balance
        self.risk_per_trade = risk_per_trade
        self.max_daily_loss = max_daily_loss
        self.max_open_trades = max_open_trades
        self.current_open_trades = 0
        self.daily_loss = 0.0

    def can_open_trade(self, risk_amount: float) -> bool:
        if self.current_open_trades >= self.max_open_trades:
            return False
        if (self.daily_loss + risk_amount) > (self.max_daily_loss * self.initial_balance):
            return False
        return True

    def calculate_position_size(self, stop_loss: float, entry_price: float) -> float:
        risk_per_trade_amount = self.risk_per_trade * self.initial_balance
        risk_per_unit = abs(entry_price - stop_loss) / entry_price
        if risk_per_unit == 0:
            return 0
        position_size = risk_per_trade_amount / risk_per_unit
        return position_size

    def register_trade_open(self):
        self.current_open_trades += 1

    def register_trade_close(self, pnl: float):
        self.current_open_trades = max(0, self.current_open_trades - 1)
        if pnl < 0:
            self.daily_loss += abs(pnl)

    def reset_daily_loss(self):
        self.daily_loss = 0.0
