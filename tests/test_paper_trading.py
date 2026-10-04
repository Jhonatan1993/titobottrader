import unittest
from paper_trading.executor import PaperTradeExecutor, PaperTrade

class TestPaperTrading(unittest.TestCase):
    def setUp(self):
        self.executor = PaperTradeExecutor()

    def test_open_and_close_trade(self):
        trade = self.executor.open_trade(
            timestamp="2026-09-20T20:15:00",
            symbol="BTCUSDT",
            timeframe="15m",
            side="BUY",
            entry_price=10000.0,
            stop_loss=9900.0,
            take_profit=10500.0,
            position_size=1.0,
            risk_amount=50.0,
            signal_score=78,
            ai_confidence=74,
            reason="Test trade"
        )
        self.assertEqual(trade.status, "OPEN")
        self.executor.close_trade(trade, exit_price=10400.0, result="CLOSED")
        self.assertEqual(trade.status, "CLOSED")
        self.assertAlmostEqual(trade.pnl, 400.0)
        self.assertIsNotNone(trade.exit_timestamp)

if __name__ == "__main__":
    unittest.main()
