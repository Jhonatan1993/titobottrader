import datetime
import random
import time
from typing import Dict, List, Any
from ai_analysis.adaptive_learning import AdaptiveLearningEngine
from ai_analysis.regime_detector import MarketRegimeDetector
from ai_analysis.funding_arbitrage import FundingArbitrageScanner
from ai_analysis.news_sentiment_shield import NewsMacroShield

ASSET_RISK_PROFILES = {
    # === FOREX CFD IQ Option — Pares Mayores y Cruces (R:R mínimo 2.0:1) ===
    "EURUSD": {"sl_pct": 0.0035, "tp_pct": 0.0070, "vol_type": "Forex Mayor - Alta Liquidez"},
    "GBPUSD": {"sl_pct": 0.0040, "tp_pct": 0.0080, "vol_type": "Forex Mayor - Volatilidad Media"},
    "USDJPY": {"sl_pct": 0.0035, "tp_pct": 0.0070, "vol_type": "Forex Mayor - Dinámica Asiática"},
    "AUDUSD": {"sl_pct": 0.0038, "tp_pct": 0.0076, "vol_type": "Forex Mayor - Commodities"},
    "USDCAD": {"sl_pct": 0.0035, "tp_pct": 0.0070, "vol_type": "Forex Mayor - Petróleo / CAD"},
    "USDCHF": {"sl_pct": 0.0034, "tp_pct": 0.0068, "vol_type": "Forex Mayor - Refugio Seguro"},
    "NZDUSD": {"sl_pct": 0.0040, "tp_pct": 0.0080, "vol_type": "Forex Mayor - Oceanía"},
    "EURGBP": {"sl_pct": 0.0030, "tp_pct": 0.0060, "vol_type": "Cruce Forex - Europeo"},
    "EURJPY": {"sl_pct": 0.0045, "tp_pct": 0.0090, "vol_type": "Cruce Forex - Volatilidad Media"},
    "GBPJPY": {"sl_pct": 0.0055, "tp_pct": 0.0110, "vol_type": "Cruce Forex - Alta Volatilidad"},
    # === COMMODITIES & WALL STREET (R:R mínimo 2.0:1) ===
    "XAUUSD": {"sl_pct": 0.0060, "tp_pct": 0.0120, "vol_type": "Commodity - Oro Spot"},
    "AAPL": {"sl_pct": 0.0080, "tp_pct": 0.0160, "vol_type": "Wall Street - Apple CFD"},
    "TSLA": {"sl_pct": 0.0120, "tp_pct": 0.0240, "vol_type": "Wall Street - Tesla CFD"},
    "NVDA": {"sl_pct": 0.0120, "tp_pct": 0.0240, "vol_type": "Wall Street - Nvidia CFD"}
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

    def update_learning_from_disk(self, product_mode: str = None):
        if product_mode in {"FOREX_CFD", "BINARY_OPTIONS"}:
            if product_mode != self.learner.product_mode:
                self.learner.cooldowns.clear()
                self.learner._cleared_cooldown_syms.clear()
            self.learner.product_mode = product_mode
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
        price = float(asset.get("price", 1.0))
        rsi = float(asset.get("rsi", 50.0))
        ema20 = float(asset.get("ema20", price))
        ema50 = float(asset.get("ema50", price))
        ema200 = float(asset.get("ema200", asset.get("ema_trend", 0.0)))
        atr = float(asset.get("atr", 0.0))
        support = float(asset.get("support", price * 0.98))
        resistance = float(asset.get("resistance", price * 1.02))
        name = asset.get("name", symbol)
        icon = asset.get("icon", "📈")
        is_open = symbol in current_positions

        clean_sym = symbol.replace("-OTC", "").replace("OTC", "")
        profile = ASSET_RISK_PROFILES.get(symbol, ASSET_RISK_PROFILES.get(clean_sym, {"sl_pct": 0.015, "tp_pct": 0.040, "vol_type": "Estándar"}))
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

            # B. Salida por Stop Loss o Trailing Stop
            elif price <= current_sl:
                decision = "SELL"
                score = 95
                confidence = 92
                action_type = "STOP_LOSS"
                if current_sl >= entry_price:
                    reason_simple = f"🔒 Trailing Stop activado en {name}: Cerramos con beneficio retenido de +{pnl_pct:.2f}%."
                else:
                    reason_simple = f"🛡️ Escudo Stop-Loss en {name}: Pérdida mínima controlada de {pnl_pct:.2f}% para preservar capital."

            # C. Salida preventiva por sobrecompra extrema (RSI > 82) con ganancia
            elif rsi > 82 and pnl_pct > 1.4:
                decision = "SELL"
                score = 88
                confidence = 90
                action_type = "CIERRE_PREVENTIVO"
                reason_simple = f"⚡ Sobrecompra extrema en {name} (RSI {rsi:.1f}). Aseguramos ganancias antes del pullback."

            # D. Salida por Cosecha Cuantitativa de Beneficios a la Bóveda (Profit Harvesting):
            elif ((pos.get("category") in ["TRADFI_STOCK", "ETF"] and (pnl_pct >= 0.85 or (pnl_pct >= 0.55 and rsi >= 56.0))) or
                  (pos.get("category") not in ["TRADFI_STOCK", "ETF"] and (pnl_pct >= 1.80 or (pnl_pct >= 1.20 and rsi >= 60.0)))):
                decision = "SELL"
                score = 92
                confidence = 94
                action_type = "COSECHA_BOVEDA"
                reason_simple = f"🏛️ Cosecha a Bóveda en {name}: Asegurando beneficio de +{pnl_pct:.2f}% para blindar en la Bóveda."

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
        macro_check = self.sentiment_shield.is_macro_environment_safe(symbol=symbol)
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

        # 4. FILTRO DE RÉGIMEN DE MERCADO (VOLATILIDAD CAÓTICA / SHOCK GLOBAL)
        can_buy_regime = regime_info.get("allow_buy", True)
        can_sell_regime = regime_info.get("allow_sell", True)
        if not can_buy_regime and not can_sell_regime:
            return {
                "symbol": symbol,
                "name": name,
                "icon": icon,
                "decision": "HOLD",
                "action_type": "REGIME_FILTER",
                "confidence": int(35 * regime_info.get("confidence_mod", 1.0)),
                "score": 30,
                "reason_simple": f"{regime_info['tag']}: Operaciones pausadas ({regime_info['reason']}).",
                "price": price,
                "take_profit": suggested_tp,
                "stop_loss": suggested_sl,
                "budget_percent": 0.0,
                "regime": regime_info["regime"],
                "regime_tag": regime_info["tag"]
            }

        # 5. EVALUACIÓN DE ENTRADAS CON CRITERIO CUANTITATIVO Y CONFLUENCIA MULTIVARIABLE
        base_kelly = self.learner.get_optimal_kelly_budget(symbol, base_budget_pct=22.0)
        kelly_budget = round(max(5.0, min(35.0, base_kelly * regime_info.get("kelly_mod", 1.0))), 1)

        # Normalización adaptativa de margen de resistencia y soporte (ATR + %):
        atr_eff = atr if atr > 0 else (price * 0.003)
        runway_atr = max(0.0, (resistance - price) / atr_eff) if resistance > price else 0.0
        bear_runway_atr = max(0.0, (price - support) / atr_eff) if price > support else 0.0
        dist_to_resistance = ((resistance - price) / price) * 100 if price > 0 else 0.0
        dist_to_support = ((price - support) / price) * 100 if price > 0 else 0.0

        # Moduladores de confianza diferenciados para compras y ventas según régimen
        bull_regime_mod = regime_info.get("confidence_mod", 1.0)
        bear_regime_mod = regime_info.get("confidence_mod", 1.0)
        if regime_info.get("regime") == "TRENDING_BEAR":
            bull_regime_mod = regime_info.get("confidence_mod_buy", 0.50)
            bear_regime_mod = regime_info.get("confidence_mod", 1.20)
        elif regime_info.get("regime") == "TRENDING_BULL":
            bull_regime_mod = regime_info.get("confidence_mod", 1.20)
            bear_regime_mod = 0.50

        confidence_boost_bull = self.learner.get_asset_confidence_boost(symbol) * bull_regime_mod
        confidence_boost_bear = self.learner.get_asset_confidence_boost(symbol) * bear_regime_mod

        # Ajuste dinámico de TP según régimen
        if regime_info.get("tp_multiplier", 1.0) != 1.0:
            suggested_tp = round(price * (1.0 + (adaptive_levels["tp_pct"] * regime_info["tp_multiplier"])), 2 if price < 1000 else 1)

        # Matriz Cuantitativa Determinística de Confluencia Multivariable (Alcista):
        # 1. Alineación de Tendencia y Medias Móviles (0 - 30 pts)
        trend_score = 0
        if price >= ema20 and ema20 >= ema50:
            trend_score = 25
        elif price >= ema20:
            trend_score = 12
        elif ema20 >= ema50:
            trend_score = 8
        else:
            trend_score = 0

        # Filtro Institucional Macro EMA 200:
        if ema200 > 0:
            if price < ema200:
                trend_score = max(0, trend_score - 15)  # Penalizar compra bajo la media de 200
            elif price >= ema200 and ema20 >= ema50:
                trend_score = min(30, trend_score + 5)   # Bonificación por tendencia macro alcista

        # 2. Impulso y Momentum RSI (0 - 30 pts): Rango óptimo de impulso alcista 46-62
        rsi_score = 0
        if 46.0 <= rsi <= 62.0:
            rsi_score = 30
        elif 42.0 <= rsi < 46.0:
            rsi_score = 22
        elif 62.0 < rsi <= 66.0:
            rsi_score = 20
        elif 36.0 <= rsi < 42.0:
            rsi_score = 12
        else:
            rsi_score = 0

        # 3. Margen Libre hacia Resistencia / Runway Alcista (0 - 20 pts)
        runway_score = 0
        if runway_atr >= 1.5 or dist_to_resistance >= 1.2:
            runway_score = 20
        elif runway_atr >= 1.0 or dist_to_resistance >= 0.8:
            runway_score = 15
        elif runway_atr >= 0.5 or dist_to_resistance >= 0.3:
            runway_score = 10
        elif runway_atr >= 0.2 or dist_to_resistance >= 0.08:
            runway_score = 5
        else:
            runway_score = 0

        # 4. Soporte y Dinámica de Cambio 24h (0 - 20 pts)
        change_24h = asset.get("change_24h", 0.0)
        support_atr = max(0.0, (price - support) / atr_eff) if price > support else 0.0
        support_score = 0
        if support_atr >= 0.4 or dist_to_support >= 0.04:
            support_score += 10
        if -3.0 <= change_24h <= 5.0:
            support_score += 10

        total_confluence = trend_score + rsi_score + runway_score + support_score
        adjusted_conf = min(98, max(20, int(total_confluence * confidence_boost_bull)))

        # Matriz Cuantitativa para Operaciones Bajistas (PUT / Venta en Corto):
        # 1. Alineación de Tendencia Bajista (0 - 30 pts)
        bear_trend_score = 0
        if price <= ema20 and ema20 <= ema50:
            bear_trend_score = 25
        elif price <= ema20:
            bear_trend_score = 12
        elif ema20 <= ema50:
            bear_trend_score = 8
        else:
            bear_trend_score = 0

        # Filtro Institucional Macro EMA 200:
        if ema200 > 0:
            if price > ema200:
                bear_trend_score = max(0, bear_trend_score - 15)  # Penalizar venta sobre la media de 200
            elif price <= ema200 and ema20 <= ema50:
                bear_trend_score = min(30, bear_trend_score + 5)   # Bonificación por tendencia macro bajista

        # 2. Impulso y Momentum Bajista (0 - 30 pts): Rango óptimo 38-54
        bear_rsi_score = 0
        if 38.0 <= rsi <= 54.0:
            bear_rsi_score = 30
        elif 34.0 <= rsi < 38.0:
            bear_rsi_score = 22
        elif 54.0 < rsi <= 58.0:
            bear_rsi_score = 20
        elif 58.0 < rsi <= 64.0:
            bear_rsi_score = 12
        elif rsi >= 70.0:
            bear_rsi_score = 25  # Fuerte rechazo por sobrecompra
        else:
            bear_rsi_score = 0

        # 3. Margen Libre hacia Soporte / Runway Bajista (0 - 20 pts)
        bear_runway_score = 0
        if bear_runway_atr >= 1.5 or dist_to_support >= 1.2:
            bear_runway_score = 20
        elif bear_runway_atr >= 1.0 or dist_to_support >= 0.8:
            bear_runway_score = 15
        elif bear_runway_atr >= 0.5 or dist_to_support >= 0.3:
            bear_runway_score = 10
        elif bear_runway_atr >= 0.2 or dist_to_support >= 0.08:
            bear_runway_score = 5
        else:
            bear_runway_score = 0

        # 4. Resistencia y Dinámica de Cambio 24h Bajista (0 - 20 pts)
        res_atr = max(0.0, (resistance - price) / atr_eff) if resistance > price else 0.0
        bear_res_score = 0
        if res_atr >= 0.4 or dist_to_resistance >= 0.04:
            bear_res_score += 10
        if -5.0 <= change_24h <= 3.0:
            bear_res_score += 10

        bear_confluence = bear_trend_score + bear_rsi_score + bear_runway_score + bear_res_score
        adjusted_conf_bear = min(98, max(20, int(bear_confluence * confidence_boost_bear)))

        # Condición Cuantitativa Estricta de COMPRA (CALL / Largo):
        if can_buy_regime and total_confluence >= 70 and adjusted_conf >= 75 and rsi < 68:
            decision = "BUY"
            score = adjusted_conf
            action_type = "COMPRA_ALCISTA_CONFIRMADA"
            reason_simple = f"🌟 Confluencia Alcista A+ ({total_confluence}/100): {name} ({profile['vol_type']}) - Tendencia {trend_score}p, RSI {rsi:.1f} {rsi_score}p, Margen a ${resistance:,.2f} {runway_score}p."
        # Condición Cuantitativa Estricta de VENTA / BAJA (PUT / Corto):
        elif can_sell_regime and bear_confluence >= 70 and adjusted_conf_bear >= 75 and rsi > 32:
            decision = "SELL"
            score = adjusted_conf_bear
            action_type = "VENTA_BAJISTA_CONFIRMADA"
            reason_simple = f"🌟 Confluencia Bajista A+ ({bear_confluence}/100): {name} ({profile['vol_type']}) - Tendencia {bear_trend_score}p, RSI {rsi:.1f} {bear_rsi_score}p, Margen a soporte ${support:,.2f} {bear_runway_score}p."
        else:
            decision = "HOLD"
            score = max(adjusted_conf, adjusted_conf_bear)
            action_type = "MONITOREO_ESTABLE"
            reasons = []
            if max(trend_score, bear_trend_score) < 20:
                reasons.append("tendencia EMA en espera")
            if max(rsi_score, bear_rsi_score) < 18:
                reasons.append(f"RSI ({rsi:.1f}) neutral")
            if max(runway_score, bear_runway_score) < 10:
                reasons.append("margen acotado")
            reason_details = ", ".join(reasons) if reasons else f"confluencia {max(total_confluence, bear_confluence)}/100"
            reason_simple = f"En espera: {name} consolidando ({reason_details})."

        final_conf = score
        final_score = score

        # Cálculo dinámico institucional de SL y TP con Ratio R:R mínimo 1:2.0
        # En Forex CFD, el SL debe tener un suelo mínimo absoluto basado en profile['sl_pct'] (mínimo 0.35% a 0.55%, o 25-50 pips)
        # para que el spread del broker (1.5 - 2.5 pips) no asfixie la posición inmediatamente tras abrir.
        sl_pct_floor = profile.get("sl_pct", 0.0035)
        min_sl_dist = price * sl_pct_floor
        sl_dist = max(min_sl_dist, 2.0 * atr) if atr > 0 else min_sl_dist
        tp_dist = max(sl_dist * 2.0, 4.0 * atr) if atr > 0 else (sl_dist * 2.0)

        decimals = 4 if price < 10.0 else (2 if price < 1000 else 1)
        if decision == "SELL":
            final_sl = round(price + sl_dist, decimals)
            final_tp = round(price - tp_dist, decimals)
            if support and support < price:
                capped_tp = round(support * 1.002, decimals)
                if capped_tp < price * 0.995:
                    final_tp = max(final_tp, capped_tp)
        else:
            final_sl = round(price - sl_dist, decimals)
            final_tp = round(price + tp_dist, decimals)
            if resistance and resistance > price:
                capped_tp = round(resistance * 0.998, decimals)
                if capped_tp > price * 1.005:
                    final_tp = min(final_tp, capped_tp)

        return {
            "symbol": symbol,
            "name": name,
            "icon": icon,
            "decision": decision,
            "action_type": action_type,
            "confidence": final_conf,
            "score": final_score,
            "reason_simple": reason_simple,
            "price": price,
            "take_profit": final_tp,
            "stop_loss": final_sl,
            "budget_percent": kelly_budget,
            "regime": regime_info["regime"],
            "regime_tag": regime_info["tag"]
        }
