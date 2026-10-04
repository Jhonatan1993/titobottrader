import math
from typing import Dict, Any

class MarketRegimeDetector:
    """
    Detector Cuantitativo de Regímenes de Mercado.
    Clasifica la dinámica de cada activo en 4 regímenes institucionales:
    1. TRENDING_BULL: Tendencia alcista sólida y confluente.
    2. TRENDING_BEAR: Presión bajista estructurada.
    3. RANGING_SIDEWAYS: Mercado lateral en consolidación.
    4. HIGH_VOLATILITY_CHAOTIC: Volatilidad anómala o velas de pánico/noticias.
    
    Proporciona moduladores dinámicos para el Criterio de Kelly, Take-Profit y Confianza.
    """
    def __init__(self):
        self.default_atr_baseline = 0.015  # 1.5% de volatilidad diaria estándar

    def detect_regime(self, asset: Dict[str, Any]) -> Dict[str, Any]:
        price = float(asset.get("price", 0.0))
        if price <= 0:
            return self._fallback_regime("PRICE_INVALID")

        ema20 = float(asset.get("ema20", price))
        ema50 = float(asset.get("ema50", price))
        rsi = float(asset.get("rsi", 50.0))
        volatility = float(asset.get("volatility", self.default_atr_baseline))
        support = float(asset.get("support", price * 0.98))
        resistance = float(asset.get("resistance", price * 1.02))

        # Distancias y relaciones
        ema_spread_pct = ((ema20 - ema50) / ema50) * 100 if ema50 > 0 else 0.0
        price_to_ema20_pct = ((price - ema20) / ema20) * 100 if ema20 > 0 else 0.0
        range_span_pct = ((resistance - support) / price) * 100 if price > 0 else 2.0

        # Ratio de volatilidad actual vs línea base institucional
        vol_ratio = volatility / self.default_atr_baseline if self.default_atr_baseline > 0 else 1.0

        # 1. RÉGIMEN CAÓTICO / ALTA VOLATILIDAD DE SHOCK
        if vol_ratio >= 2.2 or (rsi > 85.0 or rsi < 18.0):
            return {
                "regime": "HIGH_VOLATILITY_CHAOTIC",
                "tag": "⚡ Volatilidad Caótica / Shock",
                "confidence_mod": 0.65,
                "kelly_mod": 0.50,         # Reducción a la mitad del capital
                "tp_multiplier": 0.85,     # TPs defensivos y cercanos
                "sl_multiplier": 0.80,     # Stop-Loss ceñido
                "allow_buy": False,        # Prohibir compras durante caos
                "reason": f"Volatilidad realizada disparada ({vol_ratio:.1f}x) o RSI extremo ({rsi:.1f})."
            }

        # 2. RÉGIMEN DE TENDENCIA ALCISTA ESTRUCTURADA (BULL)
        if ema20 > ema50 * 1.002 and price >= ema20 * 0.995 and (46.0 <= rsi <= 72.0):
            return {
                "regime": "TRENDING_BULL",
                "tag": "🚀 Tendencia Alcista Estructurada",
                "confidence_mod": 1.20,
                "kelly_mod": 1.25,         # Aumentar asignación por viento a favor
                "tp_multiplier": 1.25,     # Dejar correr ganancias con TPs más amplios
                "sl_multiplier": 1.00,
                "allow_buy": True,
                "reason": f"Alineación alcista EMA20/50 (+{ema_spread_pct:.2f}%) con RSI sólido ({rsi:.1f})."
            }

        # 3. RÉGIMEN DE TENDENCIA BAJISTA (BEAR)
        if ema20 < ema50 * 0.998 and price <= ema20 * 1.005 and rsi < 44.0:
            return {
                "regime": "TRENDING_BEAR",
                "tag": "📉 Presión Bajista Dominante",
                "confidence_mod": 0.50,
                "kelly_mod": 0.50,
                "tp_multiplier": 0.80,
                "sl_multiplier": 0.75,
                "allow_buy": False,        # Prohibir compras contra tendencia
                "reason": f"Tendencia bajista EMA20 por debajo de EMA50 ({ema_spread_pct:.2f}%)."
            }

        # 4. RÉGIMEN LATERAL / RANGO DE CONSOLIDACIÓN
        return {
            "regime": "RANGING_SIDEWAYS",
            "tag": "🌊 Consolidación Lateral / Rango",
            "confidence_mod": 0.90,
            "kelly_mod": 0.85,
            "tp_multiplier": 1.00,
            "sl_multiplier": 0.95,
            "allow_buy": True,            # Permitir compras solo si hay confluencia estricta
            "reason": f"Mercado en compresión de rango ({range_span_pct:.1f}% entre soporte y resistencia)."
        }

    def _fallback_regime(self, code: str) -> Dict[str, Any]:
        return {
            "regime": "RANGING_SIDEWAYS",
            "tag": "⚖️ Régimen Neutral Estándar",
            "confidence_mod": 1.0,
            "kelly_mod": 1.0,
            "tp_multiplier": 1.0,
            "sl_multiplier": 1.0,
            "allow_buy": True,
            "reason": f"Inicialización neutral ({code})."
        }
