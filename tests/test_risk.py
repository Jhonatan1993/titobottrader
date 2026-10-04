import unittest
from risk_management.risk_manager import RiskManager

class TestRiskManager(unittest.TestCase):
    def setUp(self):
        self.rm = RiskManager(
            initial_balance=10000,
            risk_per_trade=0.005,
            max_daily_loss=0.02,
            max_open_trades=3,
        )

    def test_can_open_trade(self):
        self.assertTrue(self.rm.can_open_trade(50))

    def test_position_size(self):
        position_size = self.rm.calculate_position_size(stop_loss=9900, entry_price=10000)
        self.assertTrue(position_size > 0)

    def test_max_open_trades(self):
        self.rm.register_trade_open()
        self.rm.register_trade_open()
        self.rm.register_trade_open()
        self.assertFalse(self.rm.can_open_trade(50))

    def test_daily_loss_limit(self):
        self.rm.register_trade_close(-100)
        self.rm.register_trade_close(-100)
        self.assertFalse(self.rm.can_open_trade(50))

if __name__ == "__main__":
    unittest.main()
