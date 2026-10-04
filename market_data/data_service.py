import json
import os
from typing import Dict, List

from market_data.provider import MarketDataProvider


class MarketDataService:
    def __init__(self, provider: MarketDataProvider, cache_dir: str = "market_data/cache"):
        self.provider = provider
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _cache_file_path(self, symbol: str, timeframe: str) -> str:
        return os.path.join(self.cache_dir, f"{symbol}_{timeframe}.json")

    def load_cached_data(self, symbol: str, timeframe: str) -> List[Dict]:
        path = self._cache_file_path(symbol, timeframe)
        if os.path.exists(path):
            with open(path, "r") as f:
                try:
                    data = json.load(f)
                    return data if isinstance(data, list) else []
                except json.JSONDecodeError:
                    return []
        return []

    def save_cached_data(self, symbol: str, timeframe: str, data: List[Dict]):
        path = self._cache_file_path(symbol, timeframe)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def _is_valid_candle(self, candle: Dict) -> bool:
        required_fields = ["timestamp", "open", "high", "low", "close", "volume"]
        if any(field not in candle for field in required_fields):
            return False
        if not candle.get("closed", True):
            return False
        if candle["high"] < max(candle["open"], candle["close"]):
            return False
        if candle["low"] > min(candle["open"], candle["close"]):
            return False
        return True

    def _clean_data(self, candles: List[Dict]) -> List[Dict]:
        deduplicated = {}
        for candle in candles:
            if self._is_valid_candle(candle):
                deduplicated[candle["timestamp"]] = candle
        return [deduplicated[timestamp] for timestamp in sorted(deduplicated.keys())]

    def get_data(self, symbol: str, timeframe: str, start: str, end: str) -> List[Dict]:
        """
        Get market data from cache or provider.
        Uses only closed candles, removes duplicates, filters invalid candles,
        and returns candles within the requested interval.
        """
        cached = self.load_cached_data(symbol, timeframe)
        if cached:
            cleaned_cached = self._clean_data(cached)
            filtered_cache = [c for c in cleaned_cached if start <= c["timestamp"] <= end]
            if filtered_cache:
                return filtered_cache

        fetched = self.provider.get_historical_data(symbol, timeframe, start, end)
        cleaned_fetched = self._clean_data(fetched)
        self.save_cached_data(symbol, timeframe, cleaned_fetched)
        return [c for c in cleaned_fetched if start <= c["timestamp"] <= end]
