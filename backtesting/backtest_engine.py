import pandas as pd
from strategy.base_strategy import ExampleStrategy
from risk_management.risk_manager import RiskManager
from paper_trading.executor import PaperTradeExecutor
from indicators.indicators import (
    calculate_ema,
    calculate_rsi,
    calculate_macd
)

class BacktestingEngine:
    def __init__(self, initial_balance: float, risk_per_trade: float, max_daily_loss: float, max_open_trades: int):
        self.strategy = ExampleStrategy()
        self.risk_manager = RiskManager(initial_balance, risk_per_trade, max_daily_loss, max_open_trades)
        self.executor = PaperTradeExecutor()
        self.balance = initial_balance

    def run(self, df: pd.DataFrame):
        # Calculate indicators
        df["ema20"] = calculate_ema(df["close"], 20)
        df["ema50"] = calculate_ema(df["close"], 50)
        df["rsi"] = calculate_rsi(df["close"], 14)
        df["macd"], df["macd_signal"], df["macd_diff"] = calculate_macd(df["close"])

        for idx, row in df.iterrows():
            # skip rows where indicators are NaN
            if pd.isna(row["ema20"]) or pd.isna(row["ema50"]) or pd.isna(row["rsi"]):
                continue
            
            signal_data = {
                "ema20": row["ema20"],
                "ema50": row["ema50"],
                "rsi": row["rsi"],
                "macd": row["macd"]
            }
            signal = self.strategy.apply_strategy(signal_data)

            if signal["decision"] != "HOLD":
                # Simplified stop loss / take profit for demo
                entry = row["close"]
                stop_loss = entry * 0.99 if signal["decision"] == "BUY" else entry * 1.01
                take_profit = entry * 1.02 if signal["decision"] == "BUY" else entry * 0.98
                position_size = self.risk_manager.calculate_position_size(stop_loss, entry)
                risk_amount = self.risk_manager.risk_per_trade * self.risk_manager.initial_balance

                if self.risk_manager.can_open_trade(risk_amount):
                    trade = self.executor.open_trade(
                        timestamp=row["timestamp"],
                        symbol="BTCUSDT",
                        timeframe="15m",
                        side=signal["decision"],
                        entry_price=entry,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        position_size=position_size,
                        risk_amount=risk_amount,
                        signal_score=50,
                        ai_confidence=50,
                        reason=signal["reasoning"]
                    )
                    self.risk_manager.register_trade_open()
                    # For MVP, close trade next candle close price
                    if idx + 1 < len(df):
                        exit_price = df.iloc[idx + 1]["close"]
                        result = "CLOSED"
                        self.executor.close_trade(trade, exit_price, result)
                        self.risk_manager.register_trade_close(trade.pnl)
                        self.balance += trade.pnl

        return self.executor.trades
