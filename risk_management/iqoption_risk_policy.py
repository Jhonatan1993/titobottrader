"""Política de riesgo exclusiva para IQ Option.

Centraliza las barreras que deben aplicarse tanto a Forex CFD como a
opciones binarias. No calcula ni promete rentabilidad: solo autoriza o
rechaza nuevas exposiciones.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str = ""


class IQOptionRiskPolicy:
    """Circuit breaker diario y gatekeeper global de una sola posición."""

    def __init__(
        self,
        profit_target_amount: float = 0.0,
        max_loss_amount: float = 0.0,
        profit_target_enabled: bool = True,
        max_loss_enabled: bool = True,
        max_open_positions: int = 1,
        zero_loss_blocks_entries: bool = False,
    ) -> None:
        self.max_open_positions = 1 if max_open_positions != 1 else max_open_positions
        self.profit_target_amount = max(0.0, float(profit_target_amount))
        self.max_loss_amount = max(0.0, float(max_loss_amount))
        self.profit_target_enabled = bool(profit_target_enabled)
        self.max_loss_enabled = bool(max_loss_enabled)
        self.zero_loss_blocks_entries = bool(zero_loss_blocks_entries)
        self._day = self._today()
        self.realized_pnl = 0.0
        self.halted_reason: Optional[str] = None

    @property
    def halted(self) -> bool:
        return bool(self.halted_reason)

    @staticmethod
    def _today() -> str:
        return dt.datetime.now(dt.timezone.utc).date().isoformat()

    def _roll_day(self) -> None:
        today = self._today()
        if today != self._day:
            self._day = today
            self.realized_pnl = 0.0
            self.halted_reason = None

    def configure(
        self,
        profit_target_amount: float,
        max_loss_amount: float,
        profit_target_enabled: bool,
        max_loss_enabled: bool,
    ) -> None:
        self._roll_day()
        self.profit_target_amount = max(0.0, float(profit_target_amount))
        self.max_loss_amount = max(0.0, float(max_loss_amount))
        self.profit_target_enabled = bool(profit_target_enabled)
        self.max_loss_enabled = bool(max_loss_enabled)
        self._refresh_halt()

    def _refresh_halt(self) -> None:
        if (
            self.zero_loss_blocks_entries
            and self.max_loss_enabled
            and self.max_loss_amount == 0
        ):
            self.halted_reason = "TOLERANCIA_CERO_BLOQUEA_NUEVAS_ENTRADAS"
        elif self.profit_target_enabled and self.profit_target_amount > 0 and self.realized_pnl >= self.profit_target_amount:
            self.halted_reason = "META_DIARIA_ALCANZADA"
        elif (
            self.max_loss_enabled
            and self.max_loss_amount > 0
            and self.realized_pnl <= -self.max_loss_amount
        ):
            self.halted_reason = "LIMITE_PERDIDA_DIARIA_ALCANZADO"
        else:
            self.halted_reason = None

    def can_open(self, active_positions: int, pending_order: bool = False) -> RiskDecision:
        self._roll_day()
        self._refresh_halt()
        if self.halted_reason:
            return RiskDecision(False, self.halted_reason)
        if pending_order:
            return RiskDecision(False, "ORDEN_EN_TRANSITO")
        if active_positions >= self.max_open_positions:
            return RiskDecision(False, "MAXIMO_GLOBAL_DE_UNA_POSICION")
        return RiskDecision(True)

    def reset_halt(self) -> None:
        """Permite que la acción explícita del usuario ('Reanudar') reactive el bot inmediatamente."""
        self.halted_reason = None
        self.realized_pnl = 0.0
        self.zero_loss_blocks_entries = False

    def record_closed_trade(self, pnl: float) -> None:
        self._roll_day()
        self.realized_pnl = round(self.realized_pnl + float(pnl), 8)
        self._refresh_halt()

    def snapshot(self) -> dict:
        self._roll_day()
        self._refresh_halt()
        return {
            "date_utc": self._day,
            "realized_pnl": round(self.realized_pnl, 2),
            "profit_target_enabled": self.profit_target_enabled,
            "profit_target_amount": self.profit_target_amount,
            "max_loss_enabled": self.max_loss_enabled,
            "max_loss_amount": self.max_loss_amount,
            "max_open_positions": 1,
            "zero_loss_blocks_entries": self.zero_loss_blocks_entries,
            "halted": bool(self.halted_reason),
            "halted_reason": self.halted_reason,
        }
