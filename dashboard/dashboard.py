from typing import List
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from paper_trading.executor import PaperTrade

class Dashboard:
    def __init__(self):
        self.trades: List[PaperTrade] = []
        self.current_price = 0.0
        self.current_signal = "HOLD"
        self.signal_score = 0
        self.ai_confidence = 0
        self.rsi = 0
        self.macd = 0
        self.ema20 = 0
        self.ema50 = 0
        self.atr = 0
        self.support = 0
        self.resistance = 0
        self.current_balance = 0
        self.open_trades = 0
        self.daily_pnl = 0
        self.total_pnl = 0
        self.win_rate = 0
        self.max_drawdown = 0
        self.profit_factor = 0
        # More stats and graphical representations can be added later

    def update(self, trades: List[PaperTrade], current_price: float, signal: str,
               signal_score: int, ai_confidence: int,
               rsi: float, macd: float, ema20: float, ema50: float,
               atr: float, support: float, resistance: float,
               current_balance: float):
        self.trades = trades
        self.current_price = current_price
        self.current_signal = signal
        self.signal_score = signal_score
        self.ai_confidence = ai_confidence
        self.rsi = rsi
        self.macd = macd
        self.ema20 = ema20
        self.ema50 = ema50
        self.atr = atr
        self.support = support
        self.resistance = resistance
        self.current_balance = current_balance
        self.open_trades = sum(1 for t in trades if t.status == "OPEN")
        self.daily_pnl = sum(t.pnl for t in trades if t.status != "OPEN")
        self.total_pnl = self.daily_pnl  # Placeholder for total PnL calculation
        self.win_rate = self._calculate_win_rate()
        self.max_drawdown = self._calculate_max_drawdown()
        self.profit_factor = self._calculate_profit_factor()

    def _calculate_win_rate(self):
        wins = sum(1 for t in self.trades if t.result == "CLOSED" and t.pnl > 0)
        total = sum(1 for t in self.trades if t.result == "CLOSED")
        if total == 0:
            return 0
        return wins / total * 100

    def _calculate_max_drawdown(self):
        # Placeholder for drawdown calculation
        return 0

    def _calculate_profit_factor(self):
        gross_profit = sum(t.pnl for t in self.trades if t.pnl and t.pnl > 0)
        gross_loss = -sum(t.pnl for t in self.trades if t.pnl and t.pnl < 0)
        if gross_loss == 0:
            return float('inf')
        return gross_profit / gross_loss

    def display_summary(self):
        print(f"Current Price: {self.current_price}")
        print(f"Signal: {self.current_signal} (Score: {self.signal_score})")
        print(f"AI Confidence: {self.ai_confidence}")
        print(f"RSI: {self.rsi}")
        print(f"MACD: {self.macd}")
        print(f"EMA20: {self.ema20}")
        print(f"EMA50: {self.ema50}")
        print(f"ATR: {self.atr}")
        print(f"Support: {self.support}")
        print(f"Resistance: {self.resistance}")
        print(f"Current Balance: {self.current_balance}")
        print(f"Open Trades: {self.open_trades}")
        print(f"Daily PnL: {self.daily_pnl}")
        print(f"Total PnL: {self.total_pnl}")
        print(f"Win Rate: {self.win_rate:.2f}%")
        print(f"Max Drawdown: {self.max_drawdown}")
        print(f"Profit Factor: {self.profit_factor:.2f}")
