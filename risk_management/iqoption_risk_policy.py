"""Política de riesgo exclusiva para IQ Option.

Centraliza las barreras que deben aplicarse tanto a Forex CFD como a
opciones binarias. No calcula ni promete rentabilidad: solo autoriza o
rechaza nuevas exposiciones.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
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
        state_path: Optional[str] = None,
    ) -> None:
        self.max_open_positions = 1 if max_open_positions != 1 else max_open_positions
        target_value = float(profit_target_amount)
        loss_value = float(max_loss_amount)
        self.profit_target_amount = max(0.0, target_value) if math.isfinite(target_value) else 0.0
        self.max_loss_amount = max(0.0, loss_value) if math.isfinite(loss_value) else 0.0
        self.profit_target_enabled = bool(profit_target_enabled)
        self.max_loss_enabled = bool(max_loss_enabled)
        self.zero_loss_blocks_entries = bool(zero_loss_blocks_entries)
        self._day = self._today()
        self.realized_pnl = 0.0
        self.halted_reason: Optional[str] = None
        self.state_path = Path(state_path) if state_path else None
        self._closed_trade_ids: set[str] = set()
        self._state_persistence_error = False
        self._reconciliation_required = False
        self._binary_order_pending = False
        self._state_lock = threading.RLock()
        self._load_state()
        if self.state_path and not self.state_path.exists():
            self._persist_state()

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
            self._closed_trade_ids.clear()
            self._persist_state()

    def _load_state(self) -> None:
        """Restore today's reconciled PnL so a process restart cannot reset the circuit breaker."""
        if not self.state_path or not self.state_path.exists():
            return
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(state, dict) or not {"date_utc", "realized_pnl"}.issubset(state):
                raise ValueError("Invalid risk-state schema")
            if not isinstance(state.get("reconciliation_required", False), bool):
                raise ValueError("Invalid reconciliation state")
            self._reconciliation_required = state.get("reconciliation_required", False)
            if not isinstance(state.get("binary_order_pending", False), bool):
                raise ValueError("Invalid pending-order state")
            self._binary_order_pending = state.get("binary_order_pending", False)
            if state.get("date_utc") == self._day:
                self.realized_pnl = float(state.get("realized_pnl", 0.0))
                if not math.isfinite(self.realized_pnl):
                    raise ValueError("Invalid realized PnL")
                self._closed_trade_ids = {
                    str(value) for value in state.get("closed_trade_ids", []) if value
                }
                self._refresh_halt()
            else:
                self._refresh_halt()
                self._persist_state()
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # A corrupt risk snapshot must not silently authorize trading.
            self._state_persistence_error = True
            self.halted_reason = "ESTADO_RIESGO_NO_VERIFICABLE"

    def _persist_state(self) -> None:
        if not self.state_path:
            return
        if self._state_persistence_error:
            return
        temp_path = None
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_path = tempfile.mkstemp(prefix=".risk-", dir=str(self.state_path.parent))
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                os.fchmod(stream.fileno(), 0o600)
                json.dump(
                    {
                        "date_utc": self._day,
                        "realized_pnl": round(self.realized_pnl, 8),
                        "closed_trade_ids": sorted(self._closed_trade_ids)[-5000:],
                        "reconciliation_required": self._reconciliation_required,
                        "binary_order_pending": self._binary_order_pending,
                    },
                    stream,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, self.state_path)
            temp_path = None
            directory_fd = os.open(str(self.state_path.parent), os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            self._state_persistence_error = False
        except (OSError, ValueError, TypeError):
            self._state_persistence_error = True
            self.halted_reason = "ESTADO_RIESGO_NO_PERSISTIDO"
        finally:
            if temp_path is not None:
                try:
                    os.unlink(temp_path)
                except FileNotFoundError:
                    pass
                except OSError:
                    self._state_persistence_error = True
                    self.halted_reason = "ESTADO_RIESGO_NO_PERSISTIDO"

    def configure(
        self,
        profit_target_amount: float,
        max_loss_amount: float,
        profit_target_enabled: bool,
        max_loss_enabled: bool,
    ) -> None:
        with self._state_lock:
            self._roll_day()
            target_value = float(profit_target_amount)
            loss_value = float(max_loss_amount)
            if not math.isfinite(target_value) or not math.isfinite(loss_value):
                self._state_persistence_error = True
                self.halted_reason = "LIMITES_RIESGO_INVALIDOS"
                return
            self.profit_target_amount = max(0.0, target_value)
            self.max_loss_amount = max(0.0, loss_value)
            self.profit_target_enabled = bool(profit_target_enabled)
            self.max_loss_enabled = bool(max_loss_enabled)
            self._refresh_halt()
            self._persist_state()

    def _refresh_halt(self) -> None:
        if self._state_persistence_error:
            self.halted_reason = "ESTADO_RIESGO_NO_PERSISTIDO"
        elif (
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
        elif self._reconciliation_required or self._binary_order_pending:
            self.halted_reason = "RECONCILIACION_BROKER_REQUERIDA"
        else:
            self.halted_reason = None

    def can_open(self, active_positions: int, pending_order: bool = False) -> RiskDecision:
        with self._state_lock:
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
        """Refresh the halt state without erasing today's loss or overriding a risk limit."""
        with self._state_lock:
            self._roll_day()
            self._refresh_halt()

    def clear_reconciliation(self) -> None:
        """Clear reconciliation requirement when authorized."""
        with self._state_lock:
            self._roll_day()
            self._reconciliation_required = False
            self._refresh_halt()
            self._persist_state()

    def require_reconciliation(self) -> None:
        """Persist a fail-closed halt until broker-authoritative reconciliation is implemented."""
        with self._state_lock:
            self._roll_day()
            self._reconciliation_required = True
            self._refresh_halt()
            self._persist_state()

    def begin_binary_order(self) -> bool:
        """Persist intent before sending; retain it after an interrupted process."""
        with self._state_lock:
            self._roll_day()
            self._refresh_halt()
            if self.halted_reason or not self.state_path:
                return False
            self._binary_order_pending = True
            self._persist_state()
            self._refresh_halt()
            return not self._state_persistence_error

    def finish_binary_order(self) -> bool:
        """Clear intent only after a definitive rejection or completed settlement."""
        with self._state_lock:
            self._binary_order_pending = False
            self._persist_state()
            if self._state_persistence_error:
                self._binary_order_pending = True
            self._refresh_halt()
            return not self._state_persistence_error

    def record_closed_trade(self, pnl: float, trade_id: Optional[str] = None) -> None:
        with self._state_lock:
            self._roll_day()
            pnl_value = float(pnl)
            if not math.isfinite(pnl_value):
                self._state_persistence_error = True
                self.halted_reason = "ESTADO_RIESGO_NO_VERIFICABLE"
                return
            if trade_id:
                normalized_id = str(trade_id)
                if normalized_id in self._closed_trade_ids:
                    return
                self._closed_trade_ids.add(normalized_id)
            self.realized_pnl = round(self.realized_pnl + pnl_value, 8)
            self._refresh_halt()
            self._persist_state()

    def snapshot(self) -> dict:
        with self._state_lock:
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
                "reconciliation_required": self._reconciliation_required,
                "binary_order_pending": self._binary_order_pending,
                "persistence_error": self._state_persistence_error,
            }
