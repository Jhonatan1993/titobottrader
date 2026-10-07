import datetime
import random
import time
from typing import Dict, List, Any
from ai_analysis.adaptive_learning import AdaptiveLearningEngine
from ai_analysis.regime_detector import MarketRegimeDetector
from ai_analysis.funding_arbitrage import FundingArbitrageScanner
from ai_analysis.news_sentiment_shield import NewsMacroShield

ASSET_RISK_PROFILES = {
    # === TRADFI WALL STREET (Captura Binance TradFi) ===
    "META": {"sl_pct": 0.016, "tp_pct": 0.042, "vol_type": "Redes / IA Meta"},
    "MU": {"sl_pct": 0.018, "tp_pct": 0.046, "vol_type": "Semiconductores Memoria"},
    "AMD": {"sl_pct": 0.019, "tp_pct": 0.048, "vol_type": "CPUs & GPUs IA"},
    "INTC": {"sl_pct": 0.007, "tp_pct": 0.020, "vol_type": "Semiconductores Value"},
    "NVDA": {"sl_pct": 0.009, "tp_pct": 0.024, "vol_type": "Líder Hardware IA"},
    "SNDK": {"sl_pct": 0.008, "tp_pct": 0.022, "vol_type": "Hardware Almacenamiento"},
    "TSLA": {"sl_pct": 0.010, "tp_pct": 0.028, "vol_type": "Alta Volatilidad Tech"},
    "MSFT": {"sl_pct": 0.006, "tp_pct": 0.018, "vol_type": "Defensivo Cloud & Software"},
    "AAPL": {"sl_pct": 0.006, "tp_pct": 0.018, "vol_type": "Ecosistema Estable"},
    "AMZN": {"sl_pct": 0.007, "tp_pct": 0.020, "vol_type": "E-Commerce / Cloud AWS"},
    "GOOGL": {"sl_pct": 0.007, "tp_pct": 0.020, "vol_type": "Publicidad & Gemini IA"},
    "SPCX": {"sl_pct": 0.007, "tp_pct": 0.020, "vol_type": "ETF Aeroespacial"},
    "SPY": {"sl_pct": 0.005, "tp_pct": 0.014, "vol_type": "ETF Índice S&P 500"},
    "QQQ": {"sl_pct": 0.006, "tp_pct": 0.016, "vol_type": "ETF NASDAQ 100"},

    # === CRIPTOMONEDAS SPOT (Ratio Asimétrico Optimizado >= 2.0:1) ===
    "BTC": {"sl_pct": 0.010, "tp_pct": 0.025, "vol_type": "Criptomoneda Líder"},
    "ETH": {"sl_pct": 0.010, "tp_pct": 0.025, "vol_type": "Smart Contracts Cripto"},
    "SOL": {"sl_pct": 0.012, "tp_pct": 0.030, "vol_type": "Alta Velocidad Cripto"},
    "BNB": {"sl_pct": 0.010, "tp_pct": 0.025, "vol_type": "Ecosistema Binance"},
    "XRP": {"sl_pct": 0.012, "tp_pct": 0.030, "vol_type": "Pagos Globales Cripto"},
    "DOGE": {"sl_pct": 0.014, "tp_pct": 0.035, "vol_type": "Alta Volatilidad / Momentum"},
    "ADA": {"sl_pct": 0.012, "tp_pct": 0.030, "vol_type": "Smart Contracts / PoS"},
    "AVAX": {"sl_pct": 0.012, "tp_pct": 0.032, "vol_type": "DeFi / Escalabilidad"},
    "NEAR": {"sl_pct": 0.012, "tp_pct": 0.030, "vol_type": "IA & Sharding Cripto"},

    # === FOREX MAYORES (Ratio Asimétrico Institucional 2.0:1) ===
    "EURUSD": {"sl_pct": 0.0035, "tp_pct": 0.0070, "vol_type": "Forex Mayor - Alta Liquidez"},
    "GBPUSD": {"sl_pct": 0.0040, "tp_pct": 0.0080, "vol_type": "Forex Mayor - Volatilidad Media"},
    "USDJPY": {"sl_pct": 0.0035, "tp_pct": 0.0070, "vol_type": "Forex Mayor - Dinámica Asiática"}
}

class IntelligentTradingAgent:
    """
    Agente de Trading Cuantitativo Autónomo de Alta Precisión.
    Integra confluencia técnica estricta, Criterio de Kelly, y escudo de enfriamiento dinámico.
    """
    def __init__(self):
        self.thoughts: List[Dict[str, Any]] = []
        self.learner = AdaptiveLearningEngine()
        self.regime_detector = MarketRegimeDetector()
        self.funding_scanner = FundingArbitrageScanner()
        self.sentiment_shield = NewsMacroShield()
        self.last_scan_thought_time = 0.0
        self._add_thought("Cerebro Cuantitativo Autónomo inicializado con blindaje anti-pérdidas y matriz multiactivo.", "INFO", icon="🧠")

    def _add_thought(self, message: str, level: str = "INFO", symbol: str = None, icon: str = "🤖"):
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        self.thoughts.insert(0, {
            "timestamp": now_str,
            "message": message,
            "level": level,
            "symbol": symbol,
            "icon": icon
        })
        if len(self.thoughts) > 50:
            self.thoughts.pop()

    def get_thoughts(self, limit: int = 30) -> List[Dict[str, Any]]:
        return self.thoughts[:limit]

    def update_learning_from_disk(self):
        res = self.learner.recalibrate()
        patterns = self.learner.total_patterns_learned
        level = self.learner.mastery_level
        self._add_thought(
            f"📈 Auto-Calibración Cuantitativa: {patterns} patrones analizados. Nivel: {level} | Profit Factor: {self.learner.portfolio_profit_factor}x.",
            "INFO",
            icon="⚡"
        )

    def record_trade_result(self, trade_record: Dict[str, Any]):
        """Recalibra el cerebro adaptativo inmediatamente tras el cierre de cualquier posición."""
        self.learner.recalibrate()

    def evaluate_asset(self, asset: Dict[str, Any], current_positions: Dict[str, Any]) -> Dict[str, Any]:
        symbol = asset["symbol"]
        price = asset["price"]
        rsi = asset["rsi"]
        ema20 = asset["ema20"]
        ema50 = asset["ema50"]
        support = asset["support"]
        resistance = asset["resistance"]
        name = asset["name"]
        icon = asset.get("icon", "📈")
        is_open = symbol in current_positions

        profile = ASSET_RISK_PROFILES.get(symbol, {"sl_pct": 0.015, "tp_pct": 0.040, "vol_type": "Estándar"})
        adaptive_levels = self.learner.get_adaptive_sl_tp(
            symbol=symbol,
            base_sl_pct=profile["sl_pct"],
            base_tp_pct=profile["tp_pct"],
            current_price=price,
            resistance=resistance,
            support=support
        )
        suggested_tp = adaptive_levels["suggested_tp"]
        suggested_sl = adaptive_levels["suggested_sl"]

        # 0. DETECCIÓN CUANTITATIVA DE RÉGIMEN DE MERCADO (BASE)
        regime_info = self.regime_detector.detect_regime(asset)

        # 1. EVALUAR SALIDA DE POSICIÓN ACTIVA
        if is_open:
            pos = current_positions[symbol]
            entry_price = pos["entry_price"]
            pnl_pct = ((price - entry_price) / entry_price) * 100
            current_sl = pos.get("stop_loss", suggested_sl)
            # Sincronización adaptativa: Si la resistencia técnica exige un Take-Profit más cercano para asegurar ganancias, ajustar
            if suggested_tp and suggested_tp < pos.get("take_profit", 999999):
                pos["take_profit"] = suggested_tp
            current_tp = pos.get("take_profit", suggested_tp)

            # A. Salida por Take Profit
            if price >= current_tp:
                decision = "SELL"
                score = 98
                confidence = 96
                action_type = "TOMA_GANANCIA"
                reason_simple = f"🎯 ¡Meta cumplida en {name}! Cerrando con beneficio de +{pnl_pct:.2f}%."
                self._add_thought(f"Ganancia asegurada: Vendiendo {symbol} ({name}) a ${price:,.2f} (+{pnl_pct:.2f}%).", "SUCCESS", symbol, "💰")

            # B. Salida por Stop Loss o Trailing Stop
            elif price <= current_sl:
                decision = "SELL"
                score = 95
                confidence = 92
                action_type = "STOP_LOSS"
                if current_sl >= entry_price:
                    reason_simple = f"🔒 Trailing Stop activado en {name}: Cerramos con beneficio retenido de +{pnl_pct:.2f}%."
                    self._add_thought(f"Beneficio protegido: Trailing Stop ejecutado en {symbol}.", "SUCCESS", symbol, "🔒")
                else:
                    reason_simple = f"🛡️ Escudo Stop-Loss en {name}: Pérdida mínima controlada de {pnl_pct:.2f}% para preservar capital."
                    self._add_thought(f"Escudo activado: Stop-Loss ejecutado en {symbol}.", "WARNING", symbol, "🛡️")

            # C. Salida preventiva por sobrecompra extrema (RSI > 82) con ganancia
            elif rsi > 82 and pnl_pct > 1.4:
                decision = "SELL"
                score = 88
                confidence = 90
                action_type = "CIERRE_PREVENTIVO"
                reason_simple = f"⚡ Sobrecompra extrema en {name} (RSI {rsi:.1f}). Aseguramos ganancias antes del pullback."
                self._add_thought(f"Toma preventiva de beneficios en {symbol} (RSI {rsi:.1f}).", "SUCCESS", symbol, "⚡")

            # D. Salida por Cosecha Cuantitativa de Beneficios a la Bóveda (Profit Harvesting):
            # Asegura ganancias sólidas intradía (+0.60% en TradFi / +1.20% en Cripto) y las deposita en la Bóveda protegida
            elif ((pos.get("category") in ["TRADFI_STOCK", "ETF"] and (pnl_pct >= 0.85 or (pnl_pct >= 0.55 and rsi >= 56.0))) or
                  (pos.get("category") not in ["TRADFI_STOCK", "ETF"] and (pnl_pct >= 1.80 or (pnl_pct >= 1.20 and rsi >= 60.0)))):
                decision = "SELL"
                score = 92
                confidence = 94
                action_type = "COSECHA_BOVEDA"
                reason_simple = f"🏛️ Cosecha a Bóveda en {name}: Asegurando beneficio de +{pnl_pct:.2f}% para blindar en la Bóveda."
                self._add_thought(f"Ganancia asegurada: Vendiendo {symbol} ({name}) a ${price:,.2f} (+{pnl_pct:.2f}%). Trasladando ganancia a la Bóveda.", "SUCCESS", symbol, "🏛️")

            else:
                decision = "HOLD"
                action_type = "MANTENER"
                score = 50
                confidence = 50
                reason_simple = f"Posición abierta en {name}. Rendimiento actual: {'+' if pnl_pct >= 0 else ''}{pnl_pct:.2f}%. Objetivo: ${current_tp:,.2f} (+{profile['tp_pct']*100:.1f}%)."

            return {
                "symbol": symbol,
                "name": name,
                "icon": icon,
                "decision": decision,
                "action_type": action_type,
                "confidence": confidence,
                "score": score,
                "reason_simple": reason_simple,
                "price": price,
                "take_profit": current_tp,
                "stop_loss": current_sl,
                "budget_percent": 20.0,
                "regime": regime_info["regime"],
                "regime_tag": regime_info["tag"]
            }

        # 2. FILTRO DE SEGURIDAD MACROECONÓMICA Y SENTIMIENTO (PRIORIDAD GLOBAL)
        macro_check = self.sentiment_shield.is_macro_environment_safe()
        if not macro_check["safe"]:
            return {
                "symbol": symbol,
                "name": name,
                "icon": icon,
                "decision": "HOLD",
                "action_type": "MACRO_SHIELD_PAUSE",
                "confidence": 20,
                "score": 25,
                "reason_simple": f"🛡️ Escudo Macro Activo: {macro_check['reason']}",
                "price": price,
                "take_profit": suggested_tp,
                "stop_loss": suggested_sl,
                "budget_percent": 0.0,
                "regime": regime_info["regime"],
                "regime_tag": regime_info["tag"]
            }

        # 3. VERIFICACIÓN DE ESCUDO ANTI-PÉRDIDAS (COOLDOWN POR ACTIVO)
        if self.learner.is_asset_in_cooldown(symbol):
            cooldown_rem = self.learner.asset_stats.get(symbol, {}).get("cooldown_remaining_sec", 60)
            return {
                "symbol": symbol,
                "name": name,
                "icon": icon,
                "decision": "HOLD",
                "action_type": "COOLDOWN_PROTECTOR",
                "confidence": 15,
                "score": 20,
                "reason_simple": f"🛑 Enfriamiento Activo: Activo pausado ({int(cooldown_rem)}s) por racha defensiva previa para proteger saldo.",
                "price": price,
                "take_profit": suggested_tp,
                "stop_loss": suggested_sl,
                "budget_percent": 0.0,
                "regime": regime_info["regime"],
                "regime_tag": regime_info["tag"]
            }

        # 4. FILTRO DE RÉGIMEN DE MERCADO (PERMISIVIDAD DE COMPRA)
        if not regime_info["allow_buy"]:
            return {
                "symbol": symbol,
                "name": name,
                "icon": icon,
                "decision": "HOLD",
                "action_type": "REGIME_FILTER",
                "confidence": int(40 * regime_info["confidence_mod"]),
                "score": 35,
                "reason_simple": f"{regime_info['tag']}: Compras pausadas ({regime_info['reason']}).",
                "price": price,
                "take_profit": suggested_tp,
                "stop_loss": suggested_sl,
                "budget_percent": 0.0,
                "regime": regime_info["regime"],
                "regime_tag": regime_info["tag"]
            }

        # 5. EVALUACIÓN DE ENTRADAS CON CRITERIO CUANTITATIVO Y CONFLUENCIA
        dist_to_resistance = ((resistance - price) / price) * 100
        confidence_boost = self.learner.get_asset_confidence_boost(symbol) * regime_info["confidence_mod"]
        base_kelly = self.learner.get_optimal_kelly_budget(symbol, base_budget_pct=22.0)
        kelly_budget = round(max(5.0, min(35.0, base_kelly * regime_info["kelly_mod"])), 1)

        # Ajuste dinámico de TP según régimen
        if regime_info["tp_multiplier"] != 1.0:
            suggested_tp = round(price * (1.0 + (adaptive_levels["tp_pct"] * regime_info["tp_multiplier"])), 2 if price < 1000 else 1)

        # Matriz Cuantitativa Determinística de Confluencia Multivariable:
        # 1. Alineación de Tendencia y Medias Móviles (0 - 30 pts)
        trend_score = 0
        if price >= ema20:
            trend_score += 15
        elif price >= ema20 * 0.995:
            trend_score += 8
        if ema20 >= ema50:
            trend_score += 15
        elif ema20 >= ema50 * 0.996:
            trend_score += 7

        # 2. Impulso y Momentum RSI (0 - 30 pts): Rango óptimo de impulso 45-62
        rsi_score = 0
        if 46.0 <= rsi <= 60.0:
            rsi_score = 30
        elif 42.0 <= rsi < 46.0:
            rsi_score = 22
        elif 60.0 < rsi <= 65.0:
            rsi_score = 20
        elif 36.0 <= rsi < 42.0:
            rsi_score = 12
        else:
            rsi_score = 0

        # 3. Margen Libre hacia Resistencia / Runway (0 - 20 pts)
        runway_score = 0
        if dist_to_resistance >= 2.0:
            runway_score = 20
        elif dist_to_resistance >= 1.2:
            runway_score = 15
        elif dist_to_resistance >= 0.8:
            runway_score = 10
        else:
            runway_score = 0

        # 4. Soporte y Dinámica de Cambio 24h (0 - 20 pts)
        change_24h = asset.get("change_24h", 0.0)
        dist_to_support = ((price - support) / price) * 100 if support > 0 else 1.0
        support_score = 0
        if 0.4 <= dist_to_support <= 3.8:
            support_score += 10
        if -1.5 <= change_24h <= 5.0:
            support_score += 10

        total_confluence = trend_score + rsi_score + runway_score + support_score
        adjusted_conf = min(98, max(20, int(total_confluence * confidence_boost)))

        # Condición Cuantitativa Estricta de COMPRA: Confluencia >= 80 y margen libre hacia resistencia
        if total_confluence >= 80 and dist_to_resistance >= 0.8 and rsi < 68 and adjusted_conf >= 82:
            decision = "BUY"
            score = adjusted_conf
            action_type = "COMPRA_ALCISTA_CONFIRMADA"
            reason_simple = f"🌟 Confluencia A+ ({total_confluence}/100): {name} ({profile['vol_type']}) - Tendencia {trend_score}p, RSI {rsi:.1f} {rsi_score}p, Margen a ${resistance:,.2f} {runway_score}p."
        else:
            decision = "HOLD"
            score = adjusted_conf
            action_type = "MONITOREO_ESTABLE"
            reasons = []
            if trend_score < 20:
                reasons.append("tendencia EMA débil")
            if rsi_score < 18:
                reasons.append(f"RSI ({rsi:.1f}) subóptimo")
            if runway_score < 10:
                reasons.append("resistencia cercana")
            reason_details = ", ".join(reasons) if reasons else f"confluencia {total_confluence}/100"
            reason_simple = f"En espera: {name} consolidando ({reason_details})."

        return {
            "symbol": symbol,
            "name": name,
            "icon": icon,
            "decision": decision,
            "action_type": action_type,
            "confidence": adjusted_conf,
            "score": score,
            "reason_simple": reason_simple,
            "price": price,
            "take_profit": suggested_tp,
            "stop_loss": suggested_sl,
            "budget_percent": kelly_budget,
            "regime": regime_info["regime"],
            "regime_tag": regime_info["tag"]
        }
