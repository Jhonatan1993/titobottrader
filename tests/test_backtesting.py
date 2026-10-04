import unittest
import pandas as pd
from backtesting.backtest_engine import BacktestingEngine

class TestBacktesting(unittest.TestCase):
    def setUp(self):
        self.engine = BacktestingEngine(
            initial_balance=10000,
            risk_per_trade=0.005,
            max_daily_loss=0.02,
            max_open_trades=3
        )
        data = {
            "timestamp": pd.date_range(start="2026-09-01", periods=30, freq="D").astype(str),
            "close": [10 + i for i in range(30)],
            "high": [10 + i + 1 for i in range(30)],
            "low": [9 + i for i in range(30)],
            "volume": [100 + 5*i for i in range(30)],
        }
        self.df = pd.DataFrame(data)

    def test_backtest_runs(self):
        trades = self.engine.run(self.df)
        self.assertIsInstance(trades, list)
        self.assertTrue(all(hasattr(t, 'trade_id') for t in trades))

if __name__ == "__main__":
    unittest.main()
