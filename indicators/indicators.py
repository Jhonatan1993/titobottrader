import pandas as pd
import numpy as np
from ta.trend import SMAIndicator, EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

def calculate_sma(series: pd.Series, window: int) -> pd.Series:
    sma = SMAIndicator(close=series, window=window).sma_indicator()
    return sma

def calculate_ema(series: pd.Series, window: int) -> pd.Series:
    ema = EMAIndicator(close=series, window=window).ema_indicator()
    return ema

def calculate_rsi(series: pd.Series, window: int) -> pd.Series:
    rsi = RSIIndicator(close=series, window=window).rsi()
    return rsi

def calculate_macd(series: pd.Series):
    macd_obj = MACD(close=series)
    macd = macd_obj.macd()
    macd_signal = macd_obj.macd_signal()
    macd_diff = macd_obj.macd_diff()
    return macd, macd_signal, macd_diff

def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> pd.Series:
    atr = AverageTrueRange(high=high, low=low, close=close, window=window).average_true_range()
    return atr

def calculate_volume_average(volume: pd.Series, window: int) -> pd.Series:
    return volume.rolling(window=window).mean()

# Placeholder for support and resistance detection - basic
def calculate_support_resistance(close: pd.Series, window: int = 20):
    # Very simplistic support/resistance: min and max in window
    support = close.rolling(window=window).min()
    resistance = close.rolling(window=window).max()
    return support, resistance
