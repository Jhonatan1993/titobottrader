import unittest
import pandas as pd
from indicators.indicators import (
    calculate_sma,
    calculate_ema,
    calculate_rsi,
    calculate_macd,
    calculate_atr,
    calculate_volume_average,
    calculate_support_resistance
)

class TestIndicators(unittest.TestCase):
    def setUp(self):
        data = {
            "close": [1,2,3,4,5,6,7,8,9,10],
            "high": [1,2,3,4,5,6,7,8,9,10],
            "low": [1,2,3,4,5,6,7,8,9,10],
            "volume": [10,20,30,40,50,60,70,80,90,100],
        }
        self.df = pd.DataFrame(data)

    def test_sma(self):
        sma = calculate_sma(self.df["close"], 3)
        self.assertEqual(len(sma), len(self.df))
        self.assertAlmostEqual(sma.iloc[2], 2.0)

    def test_ema(self):
        ema = calculate_ema(self.df["close"], 3)
        self.assertEqual(len(ema), len(self.df))
        self.assertFalse(pd.isna(ema.iloc[-1]))
        self.assertTrue(ema.iloc[-1] > 0)

    def test_rsi(self):
        rsi = calculate_rsi(self.df["close"], 3)
        self.assertEqual(len(rsi), len(self.df))
        self.assertTrue(0 <= rsi.iloc[-1] <= 100)

    def test_macd(self):
        macd, signal, diff = calculate_macd(self.df["close"])
        self.assertEqual(len(macd), len(self.df))
        self.assertEqual(len(signal), len(self.df))
        self.assertEqual(len(diff), len(self.df))

    def test_atr(self):
        atr = calculate_atr(self.df["high"], self.df["low"], self.df["close"], 3)
        self.assertEqual(len(atr), len(self.df))

    def test_volume_average(self):
        vol_avg = calculate_volume_average(self.df["volume"], 3)
        self.assertEqual(len(vol_avg), len(self.df))
        self.assertAlmostEqual(vol_avg.iloc[2], 20)

    def test_support_resistance(self):
        support, resistance = calculate_support_resistance(self.df["close"], 3)
        self.assertEqual(len(support), len(self.df))
        self.assertEqual(len(resistance), len(self.df))
        self.assertEqual(support.iloc[2], 1)

if __name__ == "__main__":
    unittest.main()
