from abc import ABC, abstractmethod

class MarketDataProvider(ABC):
    @abstractmethod
    def get_historical_data(self, symbol: str, timeframe: str, start: str, end: str):
        """
        Retrieve historical market data for the given symbol and timeframe between start and end timestamps.
        Returns a list of candles with timestamp, open, high, low, close, volume.
        """
        pass
