import unittest
from strategy.base_strategy import ExampleStrategy

class TestStrategy(unittest.TestCase):
    def setUp(self):
        self.strategy = ExampleStrategy()

    def test_simple_buy_signal(self):
        data = {
            "ema20": 10,
            "ema50": 5,
            "rsi": 50,
            "macd": 1
        }
        result = self.strategy.apply_strategy(data)
        self.assertEqual(result["decision"], "BUY")

    def test_simple_sell_signal(self):
        data = {
            "ema20": 5,
            "ema50": 10,
            "rsi": 50,
            "macd": -1
        }
        result = self.strategy.apply_strategy(data)
        self.assertEqual(result["decision"], "SELL")

    def test_hold_signal(self):
        data = {
            "ema20": 10,
            "ema50": 10,
            "rsi": 50,
            "macd": 0
        }
        result = self.strategy.apply_strategy(data)
        self.assertEqual(result["decision"], "HOLD")

if __name__ == "__main__":
    unittest.main()
