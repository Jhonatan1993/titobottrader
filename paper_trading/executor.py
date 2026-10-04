import datetime
from typing import Dict, List

class PaperTrade:
    def __init__(self, trade_id, timestamp, symbol, timeframe, side, entry_price,
                 stop_loss, take_profit, position_size, risk_amount, signal_score, ai_confidence,
                 reason):
        self.trade_id = trade_id
        self.timestamp = timestamp
        self.symbol = symbol
        self.timeframe = timeframe
        self.side = side
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.position_size = position_size
        self.risk_amount = risk_amount
        self.signal_score = signal_score
        self.ai_confidence = ai_confidence
        self.reason = reason
        self.exit_price = None
        self.exit_timestamp = None
        self.pnl = None
        self.pnl_pct = None
        self.result = None
        self.duration = None
        self.status = "OPEN"
    
    def close(self, exit_price, result):
        self.exit_price = exit_price
        self.exit_timestamp = datetime.datetime.now().isoformat()
        self.pnl = (exit_price - self.entry_price) * self.position_size if self.side == "BUY" else (self.entry_price - exit_price) * self.position_size
        self.pnl_pct = ((self.exit_price - self.entry_price) / self.entry_price) * 100 if self.side == "BUY" else ((self.entry_price - self.exit_price) / self.entry_price) * 100
        self.result = result
        self.duration = (datetime.datetime.fromisoformat(self.exit_timestamp) - datetime.datetime.fromisoformat(self.timestamp)).total_seconds() // 60  # in minutes
        self.status = result

class PaperTradeExecutor:
    def __init__(self):
        self.trades: List[PaperTrade] = []
        self.next_trade_id = 1

    def open_trade(self, **kwargs) -> PaperTrade:
        trade = PaperTrade(trade_id=self.next_trade_id, **kwargs)
        self.next_trade_id += 1
        self.trades.append(trade)
        return trade

    def close_trade(self, trade: PaperTrade, exit_price: float, result: str):
        trade.close(exit_price, result)
