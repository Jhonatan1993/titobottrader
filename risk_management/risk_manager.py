import time
from typing import Dict, List, Optional, Any

class RiskManager:
    """
    Gestor de Riesgo Cuantitativo con blindaje integral:
    - Control de pérdida diaria (Daily Drawdown / Circuit Breaker).
    - Límite de trades simultáneos.
    - Sizing dinámico por volatilidad / distancia al Stop-Loss.
    - Cumplimiento estricto de regulación FINRA 4210: Pattern Day Trader (PDT) Shield
      para cuentas con margen y balance inferior a $25,000 USD (Máximo 3 day trades en ventana móvil de 5 días hábiles).
    """
    def __init__(
        self, 
        initial_balance: float, 
        risk_per_trade: float, 
        max_daily_loss: float, 
        max_open_trades: int,
        pdt_protection: bool = True,
        max_day_trades_5d: int = 3
    ):
        self.initial_balance = initial_balance
        self.risk_per_trade = risk_per_trade
        self.max_daily_loss = max_daily_loss
        self.max_open_trades = max_open_trades
        self.current_open_trades = 0
        self.daily_loss = 0.0
        
        # Blindaje FINRA 4210 (Pattern Day Trader)
        self.pdt_protection = pdt_protection
        self.max_day_trades_5d = max_day_trades_5d
        self.day_trades_history: List[Dict[str, Any]] = []

    def can_open_trade(
        self, 
        risk_amount: float, 
        current_equity: Optional[float] = None, 
        is_margin_account: bool = True, 
        is_tradfi: bool = False
    ) -> bool:
        # 1. Límite de cupos simultáneos
        if self.current_open_trades >= self.max_open_trades:
            return False
            
        # 2. Circuit Breaker de pérdida diaria
        if (self.daily_loss + risk_amount) > (self.max_daily_loss * self.initial_balance):
            return False
            
        # 3. Blindaje regulatorio FINRA PDT para Wall Street (acciones/ETFs)
        if is_tradfi and self.pdt_protection:
            equity = current_equity if current_equity is not None else self.initial_balance
            if self.is_pdt_restricted(current_equity=equity, is_margin_account=is_margin_account):
                return False
                
        return True

    def is_pdt_restricted(self, current_equity: float, is_margin_account: bool = True) -> bool:
        """
        Verifica si la cuenta está en riesgo de ser catalogada como Pattern Day Trader (PDT) según FINRA 4210.
        Aplica solo a cuentas de margen con equity < $25,000 USD.
        """
        if not self.pdt_protection:
            return False
        if not is_margin_account:
            return False  # Cuentas Cash están exentas de la regla PDT
        if current_equity >= 25000.0:
            return False  # Cuentas con $25,000 USD o más no tienen restricción PDT

        # Contar day trades en los últimos 5 días hábiles (~7 días naturales)
        recent_day_trades = self.get_day_trades_in_window(window_days=7)
        return recent_day_trades >= self.max_day_trades_5d

    def record_day_trade(self, symbol: str, timestamp: Optional[float] = None):
        """Registra un trade intradía completado."""
        ts = timestamp or time.time()
        self.day_trades_history.append({
            "symbol": symbol.upper(),
            "timestamp": ts
        })

    def get_day_trades_in_window(self, window_days: int = 7) -> int:
        """Retorna el número de day trades ejecutados en la ventana móvil."""
        now = time.time()
        threshold = now - (window_days * 86400)
        # Limpiar registros antiguos
        self.day_trades_history = [t for t in self.day_trades_history if t["timestamp"] >= threshold]
        return len(self.day_trades_history)

    def calculate_position_size(self, stop_loss: float, entry_price: float) -> float:
        risk_per_trade_amount = self.risk_per_trade * self.initial_balance
        risk_per_unit = abs(entry_price - stop_loss) / entry_price
        if risk_per_unit == 0:
            return 0
        position_size = risk_per_trade_amount / risk_per_unit
        return position_size

    def register_trade_open(self):
        self.current_open_trades += 1

    def register_trade_close(self, pnl: float, symbol: str = "", is_intraday: bool = False):
        self.current_open_trades = max(0, self.current_open_trades - 1)
        if pnl < 0:
            self.daily_loss += abs(pnl)
        if is_intraday and symbol:
            self.record_day_trade(symbol)

    def reset_daily_loss(self):
        self.daily_loss = 0.0

