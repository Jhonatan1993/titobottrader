import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Set, Tuple

logger = logging.getLogger("SorosRiskManager")

class SorosRiskManager:
    """
    Gestor de Riesgo Cuantitativo Avanzado:
    1. Interés Compuesto Soros Nivel 1 (Re-inversión de beneficio únicamente en racha positiva de 1 paso).
    2. Bloqueo por Racha de Pérdidas Consecutivas (Anti-Venganza Institucional).
    3. Auto-Rollover 24/7 a Medianoche (00:00 UTC) para ciclo continuo sin reiniciar servicios.
    4. Filtro de Correlación de Divisas por Minuto (Anti-Sobreexposición de cartera).
    """
    def __init__(
        self,
        base_stake: float = 10.0,
        soros_enabled: bool = False,
        max_soros_level: int = 1,
        max_consecutive_losses: int = 3
    ):
        self.base_stake = max(1.0, float(base_stake))
        self.soros_enabled = bool(soros_enabled)
        self.max_soros_level = max(1, int(max_soros_level))
        self.max_consecutive_losses = max(1, int(max_consecutive_losses))

        self.current_date = self._get_today_str()
        self.daily_pnl = 0.0
        self.daily_wins = 0
        self.daily_losses = 0
        self.consecutive_losses = 0
        self.soros_step = 0
        self.last_profit = 0.0
        
        self.active_currencies_in_minute: Set[str] = set()
        self.last_trade_minute = 0

    @staticmethod
    def _get_today_str() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def check_day_rollover(self) -> bool:
        """
        Detecta el cambio de día a las 00:00 UTC y restablece los contadores diarios automáticamente.
        """
        today = self._get_today_str()
        if today != self.current_date:
            logger.info(
                f"🔄 [Auto-Rollover 24/7] Cambio de día detectado ({self.current_date} -> {today}). "
                f"Reseteando PnL diario (${self.daily_pnl:+.2f}) y rachas a cero."
            )
            self.current_date = today
            self.daily_pnl = 0.0
            self.daily_wins = 0
            self.daily_losses = 0
            self.consecutive_losses = 0
            self.soros_step = 0
            self.last_profit = 0.0
            return True
        return False

    def can_open_trade(self) -> Tuple[bool, str]:
        """Verifica si la gestión de riesgo autoriza una nueva operación."""
        self.check_day_rollover()

        if self.consecutive_losses >= self.max_consecutive_losses:
            return False, f"Pausa preventiva: {self.consecutive_losses} pérdidas consecutivas alcanzadas. Cooldown activo para preservar capital."

        return True, "Gestor de riesgo operativo y autorizado."

    def calculate_stake(self, configured_stake: float = 0.0) -> float:
        """
        Calcula el importe de la siguiente operación.
        Si Soros Nivel 1 está activo y venimos de un WIN, arriesga: base + ganancia anterior.
        De lo contrario o tras pérdida, retorna la inversión base estricta.
        """
        base = configured_stake if configured_stake > 0 else self.base_stake

        if self.soros_enabled and self.soros_step > 0 and self.last_profit > 0:
            compounded = round(base + self.last_profit, 2)
            logger.info(f"💎 [Soros Nivel 1] Aplicando interés compuesto: Base (${base:.2f}) + Ganancia previa (${self.last_profit:.2f}) = ${compounded:.2f}")
            return compounded

        return round(base, 2)

    def register_trade_result(self, profit: float, invested: float = 0.0) -> Dict[str, Any]:
        """
        Registra el resultado monetario de la operación cerrada y modula el paso de Soros.
        """
        self.check_day_rollover()
        self.daily_pnl += profit

        if profit > 0:
            self.daily_wins += 1
            self.consecutive_losses = 0
            if self.soros_enabled and self.soros_step < self.max_soros_level:
                self.soros_step += 1
                self.last_profit = profit
            else:
                self.soros_step = 0
                self.last_profit = 0.0
            outcome = "WIN"
        elif profit < 0:
            self.daily_losses += 1
            self.consecutive_losses += 1
            self.soros_step = 0
            self.last_profit = 0.0
            outcome = "LOSS"
        else:
            self.soros_step = 0
            self.last_profit = 0.0
            outcome = "TIE"

        return {
            "outcome": outcome,
            "profit": round(profit, 2),
            "daily_pnl": round(self.daily_pnl, 2),
            "consecutive_losses": self.consecutive_losses,
            "soros_step": self.soros_step,
            "daily_wins": self.daily_wins,
            "daily_losses": self.daily_losses
        }

    def check_currency_exposure(self, asset: str, direction: str) -> bool:
        """
        Filtro de Correlación: Si en el mismo minuto ya se ejecutó una orden con
        la misma divisa base o cotizada en igual dirección, bloquea para evitar sobreexposición.
        """
        current_minute = int(time.time() // 60)
        if current_minute != self.last_trade_minute:
            self.active_currencies_in_minute.clear()
            self.last_trade_minute = current_minute

        clean_asset = str(asset).replace("-OTC", "").replace("/", "").replace("_", "")
        base_curr = clean_asset[:3].upper()
        quote_curr = clean_asset[3:6].upper() if len(clean_asset) >= 6 else ""

        key_base = f"{base_curr}_{direction.upper()}"
        key_quote = f"{quote_curr}_{direction.upper()}" if quote_curr else ""

        if key_base in self.active_currencies_in_minute or (key_quote and key_quote in self.active_currencies_in_minute):
            logger.warning(f"🛡️ Filtro de Correlación: Exposición duplicada en el mismo minuto para {base_curr}/{quote_curr} en dirección {direction}.")
            return False

        return True

    def register_currency_exposure(self, asset: str, direction: str) -> None:
        """Registra la divisa expuesta en el minuto de entrada."""
        clean_asset = str(asset).replace("-OTC", "").replace("/", "").replace("_", "")
        base_curr = clean_asset[:3].upper()
        quote_curr = clean_asset[3:6].upper() if len(clean_asset) >= 6 else ""
        
        self.active_currencies_in_minute.add(f"{base_curr}_{direction.upper()}")
        if quote_curr:
            self.active_currencies_in_minute.add(f"{quote_curr}_{direction.upper()}")

    def release_currency_exposure(self, asset: str, direction: str) -> None:
        """Libera la divisa expuesta cuando la posición ya se resolvió y cerró."""
        clean_asset = str(asset).replace("-OTC", "").replace("/", "").replace("_", "")
        base_curr = clean_asset[:3].upper()
        quote_curr = clean_asset[3:6].upper() if len(clean_asset) >= 6 else ""

        self.active_currencies_in_minute.discard(f"{base_curr}_{direction.upper()}")
        if quote_curr:
            self.active_currencies_in_minute.discard(f"{quote_curr}_{direction.upper()}")

    def manual_reset(self) -> None:
        """Permite desbloquear contadores de riesgo a mitad de sesión (vía Telegram o Dashboard)."""
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.soros_step = 0
        self.last_profit = 0.0
        self.active_currencies_in_minute.clear()
        logger.info("Contadores de riesgo y rachas reiniciados a cero.")
