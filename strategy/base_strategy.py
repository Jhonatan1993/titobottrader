from abc import ABC, abstractmethod
from typing import Dict

class Strategy(ABC):
    @abstractmethod
    def apply_strategy(self, data: Dict) -> Dict:
        """
        Apply the strategy logic on the provided market data and return a trade signal.
        """
        pass

class ExampleStrategy(Strategy):
    def apply_strategy(self, data: Dict) -> Dict:
        # Example implementation using a simple strategy
        signal = "HOLD"
        reasoning = "Neutral strategy not implemented yet."

        # Implement simplistic checks
        if data["ema20"] > data["ema50"]:
            if data["rsi"] < 70:
                signal = "BUY"
                reasoning = "EMA crossover and RSI favorable."

        elif data["ema20"] < data["ema50"]:
            if data["rsi"] > 30:
                signal = "SELL"
                reasoning = "EMA cross-under and RSI favorable for sell."

        return {
            "decision": signal,
            "reasoning": reasoning
        }
