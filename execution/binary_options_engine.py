import time
import math
import logging
from typing import Dict, Any, List, Optional

from strategy.smc_engine import SMCEngine
from ai_analysis.economic_calendar import EconomicCalendarFilter
from risk_management.soros_manager import SorosRiskManager
from telegram_service.telegram_bot import TelegramService

logger = logging.getLogger("BinaryOptionsEngine")

class BinaryOptionsStrategyEngine:
    """
    Motor Cuantitativo Especializado y 100% Aislado para Opciones Binarias (Turbo/Blitz).
    
    Características Institucionales:
    1. Gatekeeper Estricto: MÁXIMO 1 OPERACIÓN A LA VEZ (Bloqueo absoluto de aperturas múltiples).
    2. Smart Money Concepts (SMC):
       - Mitigación de Order Blocks (OB) alcistas/bajistas con memoria de 25 velas.
       - Fair Value Gaps (FVG / Imbalances) con desplazamiento institucional (1.6x ATR).
       - Barridos de Liquidez y Soportes/Resistencias Dinámicos (30 velas).
    3. Filtro Macroeconómico Institucional:
       - ForexFactory XML con bloqueo preventivo ±15 min ante noticias de Alto Impacto.
       - Enrutamiento transparente para activos OTC (24/7).
    4. Gestión de Riesgo Soros Nivel 1:
       - Interés compuesto de 1 nivel (arriesga base + ganancia previa tras acierto).
       - Retorno a la base tras 1 nivel o ante cualquier pérdida.
       - Bloqueo por racha de 3 pérdidas consecutivas.
    5. Filtro de Correlación de Divisas por Minuto (Anti-Sobreexposición de cartera).
    6. Alertas y Control Bidireccional por Telegram en tiempo real.
    """

    def __init__(self, iqoption_adapter, journal=None, learner=None, initial_balance: float = 10000.0):
        self.iq = iqoption_adapter
        self.journal = journal
        self.learner = learner
        self.initial_balance = initial_balance
        self.open_position: Optional[Dict[str, Any]] = None
        self.last_trade_time: Dict[str, float] = {}
        self.cooldown_duration: float = 120.0 # 2 minutos de descanso post-operación
        self.min_payout: float = 0.80 # 80% payout mínimo garantizado
        self.min_confidence: int = 65 # Confluencia Institucional A+
        self.default_duration_min: int = 1 # 1 minuto (Turbo 60s)
        self.total_wins: int = 0
        self.total_losses: int = 0
        self.total_ties: int = 0
        self.net_profit: float = 0.0

        # Módulos Cuantitativos Institucionales
        self.smc_engine = SMCEngine()
        self.calendar_filter = EconomicCalendarFilter(window_minutes=15)
        self.soros_manager = SorosRiskManager(
            base_stake=2.0,
            soros_enabled=True,
            max_soros_level=1,
            max_consecutive_losses=3
        )
        self.telegram = TelegramService.get_instance()

    @property
    def has_active_position(self) -> bool:
        """Indica si hay una opción binaria en curso esperando expiración."""
        if self.open_position is None:
            return False
        now = time.time()
        if now >= self.open_position.get("expiration_timestamp", 0):
            return True # Sigue activa hasta que se resuelva en el broker
        return True

    def get_status(self) -> Dict[str, Any]:
        """Estado actual del motor de opciones binarias para el dashboard y la API."""
        total_decisive = self.total_wins + self.total_losses
        win_rate = round((self.total_wins / max(1, total_decisive)) * 100, 1) if total_decisive > 0 else 0.0

        return {
            "mode": "BINARY_OPTIONS",
            "active_trade": self.open_position,
            "has_active_trade": self.has_active_position,
            "total_wins": self.total_wins,
            "total_losses": self.total_losses,
            "total_ties": self.total_ties,
            "net_profit": round(self.net_profit, 2),
            "win_rate": win_rate,
            "min_payout": self.min_payout,
            "min_confidence": self.min_confidence,
            "soros_step": self.soros_manager.soros_step,
            "soros_enabled": self.soros_manager.soros_enabled,
            "consecutive_losses": self.soros_manager.consecutive_losses,
            "daily_pnl": round(self.soros_manager.daily_pnl, 2),
            "economic_calendar": "ONLINE (ForexFactory XML)",
            "smc_engine": "ACTIVE (FVG + Order Blocks)"
        }

    def evaluate_asset(self, asset: Dict[str, Any], candles: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Analiza un activo con métodos de trading cuantitativo de alta precisión para Opciones Binarias.
        Integra Smart Money Concepts (SMC), filtro macroeconómico y gestión de riesgo.
        """
        symbol = asset.get("symbol", "")
        price = float(asset.get("price", 1.0))
        rsi = float(asset.get("rsi", 50.0))
        ema20 = float(asset.get("ema20", price))
        ema50 = float(asset.get("ema50", price))
        support = float(asset.get("support", price * 0.99))
        resistance = float(asset.get("resistance", price * 1.01))

        # 1. Filtro Macroeconómico de Calendario Económico (ForexFactory XML)
        is_safe, news_reason = self.calendar_filter.is_safe_to_trade(symbol)
        if not is_safe:
            return {
                "decision": "HOLD",
                "confidence": 10,
                "payout": 0.0,
                "reason": news_reason
            }

        # 2. Filtro de Gestión de Riesgo (Anti-Racha Negativa & Rollover Diario)
        can_open, risk_reason = self.soros_manager.can_open_trade()
        if not can_open:
            return {
                "decision": "HOLD",
                "confidence": 10,
                "payout": 0.0,
                "reason": risk_reason
            }

        # 3. Filtro de Payout (Rentabilidad matemática)
        payout = self.iq.get_payout(symbol) if hasattr(self.iq, "get_payout") else 0.85
        if payout < self.min_payout:
            return {
                "decision": "HOLD",
                "confidence": 30,
                "payout": payout,
                "reason": f"Payout insuficiente ({int(payout * 100)}% < {int(self.min_payout * 100)}% mínimo requerido)."
            }

        # 4. Filtro de Cooldown por Activo
        now = time.time()
        time_since_last = now - self.last_trade_time.get(symbol, 0.0)
        if time_since_last < self.cooldown_duration:
            rem = int(self.cooldown_duration - time_since_last)
            return {
                "decision": "HOLD",
                "confidence": 20,
                "payout": payout,
                "reason": f"Activo en enfriamiento post-operación ({rem}s restantes) para rotación segura."
            }

        # 5. Análisis Avanzado con Smart Money Concepts (SMC)
        smc_res = {}
        if candles and len(candles) >= 30:
            smc_res = self.smc_engine.analyze(candles, asset=symbol)
            # Si el motor SMC detecta mitigación de Order Block o reversión de alta confianza (>= 88%)
            if smc_res.get("decision") in ["CALL", "PUT"] and smc_res.get("confidence", 0) >= 85:
                return {
                    "decision": smc_res["decision"],
                    "confidence": smc_res["confidence"],
                    "payout": payout,
                    "reason": f"🏛️ [SMC Institucional] {smc_res['reason']}"
                }

        # 6. Análisis Tradicional de Confluencia Sniper (Mecha + S/R + RSI + EMA)
        has_bullish_rejection = False
        has_bearish_rejection = False
        last_candle_green = False
        last_candle_red = False
        if candles and len(candles) >= 1:
            prev = candles[-1]
            c_open = float(prev.get("open", price))
            c_close = float(prev.get("close", price))
            c_high = float(prev.get("high", max(c_open, c_close)))
            c_low = float(prev.get("low", min(c_open, c_close)))
            total_range = max(0.00001, c_high - c_low)
            body = abs(c_close - c_open)
            lower_wick = min(c_open, c_close) - c_low
            upper_wick = c_high - max(c_open, c_close)

            if c_close > c_open:
                last_candle_green = True
            elif c_close < c_open:
                last_candle_red = True

            if (lower_wick / total_range) >= 0.35 and lower_wick >= body:
                has_bullish_rejection = True
            if (upper_wick / total_range) >= 0.35 and upper_wick >= body:
                has_bearish_rejection = True

        # Soportes y Resistencias dinámicos estrictos de las últimas 30 velas (M1)
        if candles and len(candles) >= 3:
            recent_candles = candles[-30:] if len(candles) >= 30 else candles
            recent_lows = [float(c.get("low", c.get("close", price))) for c in recent_candles]
            recent_highs = [float(c.get("high", c.get("close", price))) for c in recent_candles]
            support = min(recent_lows)
            resistance = max(recent_highs)

        # Bandas de Bollinger cuantitativas (20 períodos, 2 dev std)
        bb_upper = resistance
        bb_lower = support
        if candles and len(candles) >= 5:
            bb_slice = candles[-20:] if len(candles) >= 20 else candles
            bb_closes = [float(c.get("close", price)) for c in bb_slice]
            bb_sma = sum(bb_closes) / len(bb_closes)
            bb_var = sum((x - bb_sma) ** 2 for x in bb_closes) / len(bb_closes)
            bb_std = math.sqrt(max(0.0, bb_var))
            bb_upper = bb_sma + 2.0 * bb_std
            bb_lower = bb_sma - 2.0 * bb_std

        change_pct = float(asset.get("change_percent", 0.0))
        trend_status = str(asset.get("trend_status", "")).upper()
        regime = str(asset.get("regime", "")).upper()
        ai_dec = str(asset.get("ai_decision", "")).upper()
        ai_conf = int(asset.get("ai_confidence", 50))

        # Filtro Anti-Lateralidad
        ma_spread = abs(ema20 - ema50) / price if price > 0 else 0
        if "RANGING" in regime and ma_spread < 0.00015 and not (has_bullish_rejection or has_bearish_rejection):
            return {
                "decision": "HOLD",
                "confidence": 25,
                "payout": payout,
                "reason": f"Mercado lateral sin dirección en {symbol} (Medias comprimidas {ma_spread*100:.3f}%)."
            }

        # Cálculo de Confluencia Institucional para CALL
        call_score = 0
        dist_support_pct = ((price - support) / price) * 100 if support > 0 else 99.0
        dist_bb_lower_pct = ((price - bb_lower) / price) * 100 if bb_lower > 0 else 99.0

        if dist_support_pct <= 0.05 or price <= bb_lower * 1.0003:
            call_score += 35
        elif dist_support_pct <= 0.15 or dist_bb_lower_pct <= 0.10:
            call_score += 25
        elif dist_support_pct <= 0.30:
            call_score += 15

        if rsi <= 38.0:
            call_score += 30
        elif rsi <= 46.0:
            call_score += 20
        elif rsi <= 54.0 and (last_candle_green or change_pct > 0):
            call_score += 15
        elif rsi >= 72.0:
            call_score -= 30

        if has_bullish_rejection:
            call_score += 25
        if last_candle_green:
            call_score += 10

        if price >= ema20 or ema20 >= ema50:
            call_score += 15
        if "ALCISTA" in trend_status or "UP" in regime or change_pct > 0.02:
            call_score += 10
        elif "BAJISTA" in trend_status and not (has_bullish_rejection or dist_support_pct <= 0.05):
            call_score -= 25

        if ai_dec in ["BUY", "CALL"]:
            call_score += 15
        if ai_conf >= 60:
            call_score += 10

        # Bonificación si SMC coincide
        if smc_res.get("decision") == "CALL":
            call_score += 20

        # Cálculo de Confluencia Institucional para PUT
        put_score = 0
        dist_resistance_pct = ((resistance - price) / price) * 100 if resistance > 0 else 99.0
        dist_bb_upper_pct = ((bb_upper - price) / price) * 100 if bb_upper > 0 else 99.0

        if dist_resistance_pct <= 0.05 or price >= bb_upper * 0.9997:
            put_score += 35
        elif dist_resistance_pct <= 0.15 or dist_bb_upper_pct <= 0.10:
            put_score += 25
        elif dist_resistance_pct <= 0.30:
            put_score += 15

        if rsi >= 62.0:
            put_score += 30
        elif rsi >= 54.0:
            put_score += 20
        elif rsi >= 46.0 and (last_candle_red or change_pct < 0):
            put_score += 15
        elif rsi <= 28.0:
            put_score -= 30

        if has_bearish_rejection:
            put_score += 25
        if last_candle_red:
            put_score += 10

        if price <= ema20 or ema20 <= ema50:
            put_score += 15
        if "BAJISTA" in trend_status or "DOWN" in regime or change_pct < -0.02:
            put_score += 10
        elif "ALCISTA" in trend_status and not (has_bearish_rejection or dist_resistance_pct <= 0.05):
            put_score -= 25

        if ai_dec in ["SELL", "PUT"]:
            put_score += 15
        if ai_conf >= 60:
            put_score += 10

        # Bonificación si SMC coincide
        if smc_res.get("decision") == "PUT":
            put_score += 20

        # Decisión Cuantitativa Institucional (>= min_confidence)
        if call_score >= self.min_confidence and call_score > put_score:
            return {
                "decision": "CALL",
                "confidence": min(98, call_score),
                "payout": payout,
                "reason": f"🎯 Confluencia Alcista Sniper ({call_score} pts): Soporte/BB ({support:.5f}), RSI {rsi:.1f} y estructura favorable en {symbol} con payout {int(payout*100)}%."
            }
        elif put_score >= self.min_confidence and put_score > call_score:
            return {
                "decision": "PUT",
                "confidence": min(98, put_score),
                "payout": payout,
                "reason": f"🎯 Confluencia Bajista Sniper ({put_score} pts): Resistencia/BB ({resistance:.5f}), RSI {rsi:.1f} y estructura favorable en {symbol} con payout {int(payout*100)}%."
            }

        return {
            "decision": "HOLD",
            "confidence": max(call_score, put_score, min(60, int(ai_conf * 0.7))),
            "payout": payout,
            "reason": f"Filtro de Calidad Activo: Confluencia insuficiente (Call: {call_score}p, Put: {put_score}p < {self.min_confidence}p requeridos)."
        }

    def trigger_test_binary_trade(
        self, 
        symbol: str = "EURJPY", 
        direction: str = "CALL", 
        amount: float = 2000.0,
        duration_minutes: int = 1
    ) -> Dict[str, Any]:
        """
        Fuerza una operación controlada de prueba en IQ Option (respetando estrictamente el cupo único 0/1).
        """
        if self.has_active_position:
            return {
                "success": False,
                "error": "GATEKEEPER ACTIVO: Ya existe 1 operación binaria en curso (1/1). Espere a su finalización."
            }
        
        dir_clean = direction.upper()
        if dir_clean not in ["CALL", "PUT"]:
            dir_clean = "CALL"

        return self.execute_binary_option(
            symbol=symbol,
            direction=dir_clean,
            amount=amount,
            duration_minutes=duration_minutes,
            is_manual_test=True
        )

    def execute_binary_option(
        self, 
        symbol: str, 
        direction: str, 
        amount: float, 
        duration_minutes: int = 1,
        entry_price: float = 0.0,
        thesis_reason: str = "Confluencia Cuantitativa Institucional",
        is_manual_test: bool = False
    ) -> Dict[str, Any]:
        """
        Dispara una opción binaria en IQ Option aplicando gestión de riesgo Soros y filtro de correlación.
        """
        if self.has_active_position:
            return {
                "success": False,
                "error": "GATEKEEPER ACTIVO: Ya existe 1 opción binaria en curso. Operaciones múltiples estrictamente bloqueadas."
            }

        dir_clean = direction.upper()
        if dir_clean not in ["CALL", "PUT"]:
            return {"success": False, "error": f"Dirección inválida {direction}. Debe ser CALL o PUT."}

        # Filtro de Correlación de Divisas en el mismo minuto (salvo pruebas manuales)
        if not is_manual_test and not self.soros_manager.check_currency_exposure(symbol, dir_clean):
            return {
                "success": False,
                "error": f"Filtro de Correlación Activo: Exposición duplicada en {symbol} para el minuto actual."
            }

        # Cálculo de Inversión con Interés Compuesto Soros Nivel 1 si aplica
        final_stake = self.soros_manager.calculate_stake(amount)

        payout = self.iq.get_payout(symbol) if hasattr(self.iq, "get_payout") else 0.85
        now = time.time()
        
        # Sincronización precisa a expiración de 1 minuto redondo
        rem_sec = int(now) % 60
        add_sec = (60 - rem_sec) if rem_sec <= 30 else (120 - rem_sec)
        expiration_ts = int(now) + add_sec + (max(1, duration_minutes) - 1) * 60

        # Ejecución en IQ Option vía Adaptador
        if hasattr(self.iq, "submit_binary_option"):
            exec_res = self.iq.submit_binary_option(
                symbol=symbol,
                direction=dir_clean,
                amount=final_stake,
                duration_minutes=duration_minutes
            )
        else:
            exec_res = {
                "success": True,
                "order_id": f"BIN_SIM_{int(now*1000)}",
                "symbol": symbol,
                "direction": dir_clean,
                "amount": final_stake,
                "payout": payout,
                "status": "OPENED"
            }

        if not exec_res.get("success"):
            return exec_res

        order_id = str(exec_res.get("order_id", f"BIN_{int(now*1000)}"))
        self.open_position = {
            "id": order_id,
            "symbol": symbol,
            "direction": dir_clean,
            "amount": float(final_stake),
            "entry_price": float(entry_price),
            "payout": payout,
            "potential_profit": round(final_stake * payout, 2),
            "entry_timestamp": now,
            "expiration_timestamp": expiration_ts,
            "duration_minutes": duration_minutes,
            "status": "OPEN",
            "thesis": thesis_reason
        }
        self.last_trade_time[symbol] = now
        self.soros_manager.register_currency_exposure(symbol, dir_clean)

        # Notificación inmediata por Telegram
        self.telegram.notify_entry(
            symbol=symbol,
            direction=dir_clean,
            stake=final_stake,
            reason=thesis_reason,
            payout=payout
        )

        logger.info(f"🚀 OPCIÓN BINARIA ABIERTA: {symbol} {dir_clean} | Monto: ${final_stake:.2f} (Soros Step {self.soros_manager.soros_step}) | Expira: {expiration_ts}")
        return {
            "success": True,
            "order_id": order_id,
            "position": self.open_position
        }

    def check_and_resolve_active_trade(self, current_price: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Método de conveniencia para liquidar la posición activa si ya expiró."""
        if not self.open_position:
            return None
        sym = self.open_position["symbol"]
        prices = {sym: current_price or self.open_position.get("entry_price", 1.0)}
        return self.check_and_resolve_positions(prices)

    def check_and_resolve_positions(self, current_prices: Dict[str, float]) -> Optional[Dict[str, Any]]:
        """
        Monitorea el vencimiento de la opción binaria activa y la liquida automáticamente.
        Actualiza el gestor Soros y emite alertas a Telegram y al Journal.
        """
        if not self.open_position:
            return None

        pos = self.open_position
        now = time.time()
        exp_ts = pos.get("expiration_timestamp", 0)

        # Si aún no ha expirado el tiempo de la opción, sigue esperando
        if now < exp_ts:
            return None

        sym = pos["symbol"]
        cur_p = current_prices.get(sym, pos["entry_price"])
        entry_p = pos["entry_price"]
        dir_clean = pos["direction"]
        invested = pos["amount"]
        payout = pos.get("payout", 0.85)

        # Determinación matemática del resultado oficial
        if dir_clean == "CALL":
            is_win = cur_p > entry_p
            is_tie = math.isclose(cur_p, entry_p, rel_tol=1e-5)
        else: # PUT
            is_win = cur_p < entry_p
            is_tie = math.isclose(cur_p, entry_p, rel_tol=1e-5)

        if is_tie:
            result_type = "TIE"
            pnl = 0.0
            self.total_ties += 1
            reason = f"Empate exacto en {sym} (Entrada {entry_p} == Cierre {cur_p}). Reembolso íntegro."
        elif is_win:
            result_type = "WIN"
            pnl = round(invested * payout, 2)
            self.total_wins += 1
            self.net_profit += pnl
            reason = f"🏆 ¡OPCIÓN BINARIA GANADA! {sym} {dir_clean}. Ganancia: +${pnl:.2f} (+{int(payout*100)}%)."
        else:
            result_type = "LOSS"
            pnl = -round(invested, 2)
            self.total_losses += 1
            self.net_profit += pnl
            reason = f"🛡️ Opción binaria finalizada en {sym}. Pérdida controlada de inversión: -${invested:.2f}."

        # Registrar resultado en SorosRiskManager y liberar exposición
        soros_res = self.soros_manager.register_trade_result(pnl, invested)
        self.soros_manager.release_currency_exposure(sym, dir_clean)

        resolution_data = {
            "order_id": pos["id"],
            "symbol": sym,
            "direction": dir_clean,
            "entry_price": entry_p,
            "exit_price": cur_p,
            "amount": invested,
            "pnl": pnl,
            "result": result_type,
            "reason": reason,
            "timestamp": now,
            "soros_step": soros_res.get("soros_step", 0),
            "daily_pnl": soros_res.get("daily_pnl", 0.0)
        }

        # Registrar en Journal de transacciones si está disponible
        if self.journal and hasattr(self.journal, "record_trade"):
            try:
                self.journal.record_trade({
                    "broker": "IQOPTION",
                    "category": "BINARY_OPTIONS",
                    "symbol": sym,
                    "side": dir_clean,
                    "entry_price": entry_p,
                    "exit_price": cur_p,
                    "invested_amount": invested,
                    "pnl": pnl,
                    "pnl_percent": (payout * 100) if is_win else (-100.0 if not is_tie else 0.0),
                    "reason": reason,
                    "exit_reason": reason
                })
            except Exception as e:
                logger.error(f"Error registrando binaria en journal: {e}")

        # Notificación inmediata por Telegram
        self.telegram.notify_result(
            symbol=sym,
            outcome=result_type,
            profit=pnl,
            daily_pnl=soros_res.get("daily_pnl", self.net_profit),
            consecutive_losses=soros_res.get("consecutive_losses", 0)
        )

        # Recalibrar IA con el resultado obtenido
        if self.learner and hasattr(self.learner, "recalibrate"):
            try:
                self.learner.recalibrate()
            except Exception:
                pass

        # LIBERAR EL GATEKEEPER DE CUPO
        self.open_position = None
        cooldown_add = 240.0 if result_type == "LOSS" else self.cooldown_duration
        self.last_trade_time[sym] = now + cooldown_add
        logger.info(f"🏁 RESOLUCIÓN BINARIA: {resolution_data['reason']}")
        return resolution_data
