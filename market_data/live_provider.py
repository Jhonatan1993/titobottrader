import asyncio
import json
import ssl
import certifi
from typing import List, Dict, Callable, Optional
import websockets

class LiveMarketDataProvider:
    def __init__(self, symbol: str, timeframe: str):
        self.symbol = symbol.lower()
        self.timeframe = timeframe
        self.ws_url = f"wss://stream.binance.com:9443/ws/{self.symbol}@kline_{self.timeframe}"
        self.callbacks: List[Callable[[Dict], None]] = []
        self.connected = False

    async def _connect(self):
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        async with websockets.connect(self.ws_url, ssl=ssl_context) as websocket:
            self.connected = True
            async for message in websocket:
                data = json.loads(message)
                candle = data["k"]
                if candle["x"]:  # only closed candles
                    candle_data = {
                        "timestamp": candle["t"],
                        "open": float(candle["o"]),
                        "high": float(candle["h"]),
                        "low": float(candle["l"]),
                        "close": float(candle["c"]),
                        "volume": float(candle["v"]),
                    }
                    for callback in self.callbacks:
                        callback(candle_data)

    def add_callback(self, callback: Callable[[Dict], None]):
        self.callbacks.append(callback)

    def start(self):
        loop = asyncio.get_event_loop()
        loop.create_task(self._connect())
        loop.run_forever()
