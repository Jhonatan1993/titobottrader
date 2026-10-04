from typing import Dict, Any

class AIAnalyzer:
    """
    Simple deterministic AI-style analyzer for MVP.
    It does not invent data and returns HOLD if required fields are missing.
    """

    REQUIRED_FIELDS = [
        "symbol",
        "timeframe",
        "price",
        "trend",
        "rsi",
        "macd",
        "ema20",
        "ema50",
        "atr",
        "volume_ratio",
        "support",
        "resistance",
    ]

    def analyze(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        missing = [field for field in self.REQUIRED_FIELDS if field not in payload or payload[field] is None]
        if missing:
            return {
                "decision": "HOLD",
                "confidence": 0,
                "reasoning": f"Missing required structured data: {', '.join(missing)}",
                "risk_level": "HIGH",
                "invalidating_conditions": [f"missing_{field}" for field in missing],
            }

        decision = "HOLD"
        confidence = 50
        risk_level = "MEDIUM"
        reasons = []

        trend = payload["trend"]
        rsi = payload["rsi"]
        macd = payload["macd"]
        price = payload["price"]
        ema20 = payload["ema20"]
        ema50 = payload["ema50"]
        support = payload["support"]
        resistance = payload["resistance"]
        volume_ratio = payload["volume_ratio"]

        if trend == "BULLISH" and ema20 > ema50 and price >= ema20 and rsi < 70 and macd > 0 and volume_ratio >= 1.0:
            decision = "BUY"
            confidence = 70
            reasons.append("Bullish alignment across trend, EMA, RSI, MACD and volume.")
        elif trend == "BEARISH" and ema20 < ema50 and price <= ema20 and rsi > 30 and macd < 0 and volume_ratio >= 1.0:
            decision = "SELL"
            confidence = 70
            reasons.append("Bearish alignment across trend, EMA, RSI, MACD and volume.")
        else:
            reasons.append("Conditions are mixed or incomplete for a directional decision.")

        if abs(price - support) < abs(price - resistance):
            reasons.append("Price is closer to support than resistance.")
        else:
            reasons.append("Price is closer to resistance than support.")

        invalidating_conditions = []
        if decision == "BUY":
            invalidating_conditions = [
                "ema20_below_ema50",
                "macd_turns_negative",
                "price_breaks_below_support",
            ]
        elif decision == "SELL":
            invalidating_conditions = [
                "ema20_above_ema50",
                "macd_turns_positive",
                "price_breaks_above_resistance",
            ]
        else:
            invalidating_conditions = [
                "insufficient_signal_confluence",
            ]

        return {
            "decision": decision,
            "confidence": confidence,
            "reasoning": " ".join(reasons),
            "risk_level": risk_level,
            "invalidating_conditions": invalidating_conditions,
        }
