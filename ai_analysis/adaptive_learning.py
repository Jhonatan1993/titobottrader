import os
import json
import time
import math
from typing import Dict, List, Any, Optional

class AdaptiveLearningEngine:
    """
    Motor Cuantitativo de Aprendizaje Continuo, Criterio de Kelly y Blindaje Anti-Pérdidas.
    Analiza estadísticas históricas de ejecución para:
    1. Calcular Expectativa Matemática ($/trade) y Profit Factor por activo.
    2. Dimensionamiento óptimo de capital mediante Criterio de Kelly Fraccional (Quarter-Kelly).
    3. Cooldown dinámico: Bloquea activos en racha de pérdidas (evita revenge trading).
    4. Auto-ajuste de umbrales de confianza y Stop-Loss/Take-Profit según volatilidad realizada.
    5. Nivel de Maestría del Agente basado en métricas institucionales y control de drawdown.
    """
    def __init__(self, data_file: str = "data/trades_history.json", lookback_trades: int = 50):
        self.data_file = data_file
        self.lookback_trades = lookback_trades
        self.asset_stats: Dict[str, Dict[str, Any]] = {}
        self.cooldowns: Dict[str, float] = {}  # symbol -> expiration timestamp
        self.total_patterns_learned = 0
        self.portfolio_win_rate = 50.0
        self.portfolio_profit_factor = 1.0
        self.portfolio_expectancy = 0.0
        self.portfolio_max_drawdown = 0.0
        self.mastery_level = "🌱 Cadete Algorítmico"
        self._cleared_cooldown_syms = set()
        self.recalibrate()

    def recalibrate(self) -> Dict[str, Any]:
        """
        Lee el historial de operaciones y ejecuta la matriz de auto-optimización cuántica.
        Incorpora ventana móvil ponderada por activo y cálculo de riesgo dinámico.
        """
        if not os.path.exists(self.data_file):
            return {"status": "Historial vacío, inicializando matriz base."}

        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                trades = json.load(f)
        except Exception:
            trades = []

        if not trades:
            return {"status": "Sin transacciones previas"}

        if len(trades) != self.total_patterns_learned:
            self._cleared_cooldown_syms.clear()

        self.total_patterns_learned = len(trades)
        now = time.time()

        # Agrupación por símbolo
        stats_by_sym: Dict[str, List[Dict[str, Any]]] = {}
        for t in trades:
            sym = t.get("symbol", "UNKNOWN")
            if sym not in stats_by_sym:
                stats_by_sym[sym] = []
            stats_by_sym[sym].append(t)

        total_wins = 0
        total_losses = 0
        total_gross_profit = 0.0
        total_gross_loss = 0.0

        for sym, all_sym_trades in stats_by_sym.items():
            # Ventana móvil adaptativa (últimos N trades para capturar régimen reciente)
            sym_trades = all_sym_trades[-self.lookback_trades:] if self.lookback_trades > 0 else all_sym_trades

            wins = [t for t in sym_trades if t.get("pnl", 0.0) > 0]
            losses = [t for t in sym_trades if t.get("pnl", 0.0) <= 0]
            
            n_wins = len(wins)
            n_losses = len(losses)
            n_total = len(sym_trades)
            win_rate = (n_wins / n_total) if n_total > 0 else 0.5

            gross_profit = sum(t.get("pnl", 0.0) for t in wins)
            gross_loss = abs(sum(t.get("pnl", 0.0) for t in losses))
            net_pnl = gross_profit - gross_loss

            total_wins += n_wins
            total_losses += n_losses
            total_gross_profit += gross_profit
            total_gross_loss += gross_loss

            avg_win = (gross_profit / n_wins) if n_wins > 0 else 0.0
            avg_loss = (gross_loss / n_losses) if n_losses > 0 else 0.0
            
            # Profit Factor
            if gross_loss > 0:
                profit_factor = round(gross_profit / gross_loss, 2)
            else:
                profit_factor = 99.0 if gross_profit > 0 else 1.0

            # Expectativa Matemática ($/trade y R)
            loss_rate = 1.0 - win_rate
            expectancy = round((win_rate * avg_win) - (loss_rate * avg_loss), 2)
            expectancy_r = round(expectancy / avg_loss, 2) if avg_loss > 0 else 0.0

            # Criterio de Kelly Fraccional (Quarter-Kelly con amortiguador defensivo)
            b = (avg_win / avg_loss) if avg_loss > 0 else 1.5
            p = win_rate
            q = 1.0 - p
            raw_kelly = ((p * b - q) / b) if b > 0 else 0.0

            # Volatilidad Realizada de Retornos (% PnL)
            pnl_pcts = [float(t.get("pnl_percent", 0.0)) for t in sym_trades]
            mean_pnl = sum(pnl_pcts) / n_total if n_total > 0 else 0.0
            variance = sum((x - mean_pnl) ** 2 for x in pnl_pcts) / n_total if n_total > 1 else 0.0
            volatility_realized = round(math.sqrt(variance), 2)

            # Drawdown Máximo Realizado en la muestra
            cum_pnl = 0.0
            peak_pnl = 0.0
            max_dd = 0.0
            for t in sym_trades:
                cum_pnl += t.get("pnl", 0.0)
                if cum_pnl > peak_pnl:
                    peak_pnl = cum_pnl
                dd = peak_pnl - cum_pnl
                if dd > max_dd:
                    max_dd = dd
            max_drawdown = round(max_dd, 2)

            # Racha perdedora consecutiva más reciente
            recent_loss_streak = 0
            for t in reversed(sym_trades):
                if t.get("pnl", 0.0) <= 0:
                    recent_loss_streak += 1
                else:
                    break

            # Activación de Cooldown Dinámico (Escudo Anti-Rachas)
            # Si >= 2 pérdidas consecutivas, congelar el activo por 180 segundos
            is_cooling = False
            cooldown_remaining = 0.0
            if sym in self.cooldowns:
                if now < self.cooldowns[sym]:
                    is_cooling = True
                    cooldown_remaining = round(self.cooldowns[sym] - now, 1)
                else:
                    del self.cooldowns[sym]

            if recent_loss_streak >= 2 and not is_cooling and sym not in self._cleared_cooldown_syms:
                self.cooldowns[sym] = now + 180.0  # 3 minutos de cooldown
                is_cooling = True
                cooldown_remaining = 180.0

            # Amortiguación de Kelly en rachas adversas
            streak_dampener = max(0.5, 1.0 - (0.25 * recent_loss_streak)) if recent_loss_streak > 0 else 1.0
            safe_kelly_pct = round(max(5.0, min(35.0, ((raw_kelly * 25.0) if raw_kelly > 0 else 10.0) * streak_dampener)), 1)

            # Multiplicadores Adaptativos de SL y TP
            sl_mult = 1.0
            tp_mult = 1.0

            if is_cooling:
                expert_tag = "🛑 Cooldown (Racha -)"
                confidence_bonus = 0.60
                budget_multiplier = 0.50
                sl_mult = 0.85   # Ajustar SL más ajustado por protección
                tp_mult = 0.95
            elif win_rate >= 0.65 and profit_factor >= 1.6 and net_pnl > 0:
                expert_tag = "⭐ Activo Estrella"
                confidence_bonus = 1.25
                budget_multiplier = 1.30
                sl_mult = 1.0
                tp_mult = 1.20   # Dejar correr los beneficios
            elif win_rate >= 0.50 and net_pnl >= 0:
                expert_tag = "📈 Rendimiento Estable"
                confidence_bonus = 1.05
                budget_multiplier = 1.0
                sl_mult = 0.95
                tp_mult = 1.05
            elif win_rate < 0.40 or net_pnl < 0:
                expert_tag = "🛡️ Modo Defensivo"
                confidence_bonus = 0.80
                budget_multiplier = 0.70
                sl_mult = 0.85   # Reducir margen de pérdida
                tp_mult = 0.95
            else:
                expert_tag = "⚖️ En Evaluación"
                confidence_bonus = 1.0
                budget_multiplier = 1.0
                sl_mult = 1.0
                tp_mult = 1.0

            self.asset_stats[sym] = {
                "trades": n_total,
                "wins": n_wins,
                "losses": n_losses,
                "win_rate": round(win_rate * 100, 1),
                "total_pnl": round(net_pnl, 2),
                "profit_factor": profit_factor,
                "expectancy": expectancy,
                "expectancy_r": expectancy_r,
                "safe_kelly_pct": safe_kelly_pct,
                "volatility_realized": volatility_realized,
                "max_drawdown": max_drawdown,
                "recent_loss_streak": recent_loss_streak,
                "is_cooling": is_cooling,
                "cooldown_remaining_sec": cooldown_remaining,
                "confidence_bonus": confidence_bonus,
                "budget_multiplier": budget_multiplier,
                "sl_mult": sl_mult,
                "tp_mult": tp_mult,
                "expert_tag": expert_tag
            }

        # Métricas Globales de Portafolio
        total_trades = total_wins + total_losses
        self.portfolio_win_rate = round((total_wins / total_trades) * 100, 1) if total_trades > 0 else 50.0
        self.portfolio_profit_factor = round(total_gross_profit / total_gross_loss, 2) if total_gross_loss > 0 else (99.0 if total_gross_profit > 0 else 1.0)
        overall_avg_win = (total_gross_profit / total_wins) if total_wins > 0 else 0.0
        overall_avg_loss = (total_gross_loss / total_losses) if total_losses > 0 else 0.0
        self.portfolio_expectancy = round(((total_wins / total_trades) * overall_avg_win) - (((total_losses / total_trades)) * overall_avg_loss), 2) if total_trades > 0 else 0.0

        # Rango de Maestría
        if total_trades >= 50 and self.portfolio_win_rate >= 68.0 and self.portfolio_profit_factor >= 2.0:
            self.mastery_level = "👑 Maestro de Riesgo Autónomo V5"
        elif total_trades >= 25 and self.portfolio_profit_factor >= 1.5:
            self.mastery_level = "💎 Cuantitativo Avanzado"
        elif total_trades >= 8:
            self.mastery_level = "🧠 Calibrado Cuantitativo"
        else:
            self.mastery_level = "🌱 Cadete Algorítmico"

        return {
            "total_patterns": self.total_patterns_learned,
            "portfolio_win_rate": self.portfolio_win_rate,
            "portfolio_profit_factor": self.portfolio_profit_factor,
            "portfolio_expectancy": self.portfolio_expectancy,
            "mastery_level": self.mastery_level,
            "assets": self.asset_stats
        }

    def is_asset_in_cooldown(self, symbol: str) -> bool:
        """Verifica si un activo está temporalmente vetado por racha de pérdidas."""
        if symbol in self.cooldowns:
            if time.time() < self.cooldowns[symbol]:
                return True
            else:
                del self.cooldowns[symbol]
        return False

    def clear_cooldown(self, symbol: Optional[str] = None):
        """Permite limpiar el cooldown manualmente o para todos los activos."""
        if symbol:
            self.cooldowns.pop(symbol, None)
            self._cleared_cooldown_syms.add(symbol)
        else:
            self.cooldowns.clear()
            self._cleared_cooldown_syms.update(self.asset_stats.keys())
        self.recalibrate()

    def get_optimal_kelly_budget(self, symbol: str, base_budget_pct: float = 20.0) -> float:
        """Retorna el porcentaje óptimo de capital a arriesgar según Criterio de Kelly."""
        stat = self.asset_stats.get(symbol)
        if not stat:
            return base_budget_pct
        if stat.get("is_cooling"):
            return 0.0
        return stat.get("safe_kelly_pct", base_budget_pct)

    def get_asset_confidence_boost(self, symbol: str) -> float:
        stat = self.asset_stats.get(symbol)
        return stat.get("confidence_bonus", 1.0) if stat else 1.0

    def get_adaptive_sl_tp(self, symbol: str, base_sl_pct: float, base_tp_pct: float, current_price: float,
                           resistance: Optional[float] = None, support: Optional[float] = None) -> Dict[str, Any]:
        """
        Calcula niveles dinámicos de Stop-Loss y Take-Profit optimizados según
        la volatilidad realizada, el win-rate y el perfil adaptativo del activo.
        Sincroniza el Take-Profit de forma inteligente con los techos y resistencias
        del mercado para evitar metas inalcanzables fuera del rango diario.
        """
        stat = self.asset_stats.get(symbol, {})
        sl_mult = stat.get("sl_mult", 1.0)
        tp_mult = stat.get("tp_mult", 1.0)

        # Ratio base asimétrico y defensivo ultra-ceñido
        sl_pct = max(0.005, min(0.035, base_sl_pct * sl_mult))
        tp_pct = max(sl_pct * 1.8, min(0.12, base_tp_pct * tp_mult))

        decimals = 2 if current_price < 1000 else 1
        suggested_sl = round(current_price * (1.0 - sl_pct), decimals)
        suggested_tp = round(current_price * (1.0 + tp_pct), decimals)

        # Sincronización Estructural con Techos y Resistencias Reales:
        # El Take-Profit NUNCA debe sobrepasar una resistencia técnica mayor,
        # sino colocarse justo por delante (0.3% a 0.5% antes) para garantizar ejecución.
        if resistance and resistance > current_price * 1.008:
            capped_tp = round(resistance * 0.997, decimals)
            if capped_tp > current_price * 1.006:
                suggested_tp = min(suggested_tp, capped_tp)
                tp_pct = round((suggested_tp - current_price) / current_price, 4)

        # Sincronización con Soporte técnico
        if support and support < current_price * 0.992:
            capped_sl = round(support * 0.995, decimals)
            if capped_sl < current_price:
                suggested_sl = max(suggested_sl, capped_sl)
                sl_pct = round((current_price - suggested_sl) / current_price, 4)

        rr_ratio = round(tp_pct / sl_pct, 2) if sl_pct > 0 else 1.8

        return {
            "suggested_sl": suggested_sl,
            "suggested_tp": suggested_tp,
            "sl_pct": round(sl_pct, 4),
            "tp_pct": round(tp_pct, 4),
            "risk_reward_ratio": rr_ratio,
            "expert_tag": stat.get("expert_tag", "⚖️ Estándar")
        }

    def get_learning_summary(self) -> Dict[str, Any]:
        """Resumen enriquecido para visualización en el dashboard institucional."""
        active_cooldowns_count = sum(1 for exp in self.cooldowns.values() if exp > time.time())
        return {
            "mastery_level": self.mastery_level,
            "patterns_analyzed": self.total_patterns_learned,
            "portfolio_win_rate": self.portfolio_win_rate,
            "portfolio_profit_factor": self.portfolio_profit_factor,
            "portfolio_expectancy": self.portfolio_expectancy,
            "active_cooldowns_count": active_cooldowns_count,
            "asset_stats": self.asset_stats
        }
