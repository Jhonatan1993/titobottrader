from typing import List
from market_data.models import Candle
from market_data.provider import MarketDataProvider
import datetime
import random

class FakeMarketDataProvider(MarketDataProvider):
    """
    A fake data provider that generates synthetic historical data for testing.
    """

    def get_historical_data(self, symbol: str, timeframe: str, start: str, end: str) -> List[dict]:
        # Parse start and end timestamps as datetime
        start_dt = datetime.datetime.fromisoformat(start)
        end_dt = datetime.datetime.fromisoformat(end)

        delta_map = {
            "5m": datetime.timedelta(minutes=5),
            "15m": datetime.timedelta(minutes=15),
            "1h": datetime.timedelta(hours=1),
            "4h": datetime.timedelta(hours=4),
        }
        delta = delta_map.get(timeframe, datetime.timedelta(minutes=15))

        candles = []
        current_time = start_dt
        price = 50000.0  # initial price for BTCUSDT

        while current_time <= end_dt:
            # generate synthetic OHLCV with random noise
            open_p = price
            close_p = price + random.uniform(-100, 100)
            high_p = max(open_p, close_p) + random.uniform(0, 50)
            low_p = min(open_p, close_p) - random.uniform(0, 50)
            volume = random.uniform(0.1, 5.0)

            candle = Candle(
                timestamp=current_time.isoformat(),
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=volume,
                closed=True
            )
            candles.append(candle.to_dict())

            price = close_p
            current_time += delta

        return candles
