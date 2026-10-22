import time
import datetime
from typing import Dict, List, Any, Optional
from market_data.market_feed import MultiAssetMarketFeed
from ai_analysis.intelligent_agent import IntelligentTradingAgent
from trade_journal.journal import TradeJournal
from config.broker_config import load_broker_config, save_broker_config
from risk_management.risk_manager import RiskManager
from risk_management.iqoption_risk_policy import IQOptionRiskPolicy
from execution.iqoption_adapter import ACTIVE_ID_TO_SYMBOL
from execution.binary_options_engine import BinaryOptionsStrategyEngine

class RealTimeTradingEngine:
    """
    Motor Central de Trading Autónomo Institucional con:
    1. Arquitectura Unificada Multiactivo (Wall Street TradFi + Cripto + ETFs)
    2. Criterio de Kelly Adaptativo & Paridad de Volatilidad
    3. Trailing Stop Dinámico Multinivel y Break-Even Protector
    4. Escudo Anti-Rachas (Cooldown Temporal de Activos en Falla)
    5. Circuit Breakers: Meta Diaria de Ganancia y Límite Máximo de Pérdida
    6. Auto-Calibración Cuantitativa Continua tras cada transacción
    """
    def __init__(self, initial_balance: Optional[float] = None, max_open_positions: int = 5, execution_environment: Optional[str] = None):
        self.broker_config = load_broker_config()
        # Modo exclusivo: IQ Option Forex CFD / Binarias
        self.operating_mode = self.broker_config.get("operating_mode", "IQ_BINARY")
        self.iq_mode = self.broker_config.get("iq_mode", "BINARY_OPTIONS")
        self.execution_environment = execution_environment or self.broker_config.get("iqoption_environment", "PAPER")
        
        saved_paper = float(self.broker_config.get("paper_initial_balance", 10000.0))
        self.paper_initial_balance = initial_balance if initial_balance is not None else saved_paper

        if self.execution_environment == "PAPER":
            self.initial_balance = self.paper_initial_balance
            self.cash_balance = self.paper_initial_balance
        else:
            self.initial_balance = initial_balance if initial_balance is not None else 10000.0
            self.cash_balance = self.initial_balance
        # Política de plataforma IQ Option: una sola exposición global, sin excepción.
        self.max_open_positions = 1
        self.is_running = True
        self._iqoption_order_pending = False

        # Gestor de Riesgo y Regulación FINRA 4210 (PDT Shield)
        self.risk_manager = RiskManager(
            initial_balance=self.initial_balance,
            risk_per_trade=0.01,
            max_daily_loss=0.05,
            max_open_trades=self.max_open_positions,
            pdt_protection=True,
            max_day_trades_5d=3
        )

        # Configuración persistente de Circuit Breakers (Meta Ganancia & Límite Pérdida)
        target_val = float(self.broker_config.get("iqoption_profit_target_amount", self.broker_config.get("profit_target_amount", 50000.0)))
        if target_val < 5000.0:
            target_val = 50000.0
        loss_val = float(self.broker_config.get("iqoption_max_loss_amount", self.broker_config.get("max_loss_amount", 10000.0)))
        if loss_val > 0 and loss_val < 2000.0:
            loss_val = 10000.0

        self.profit_target_enabled = bool(self.broker_config.get("iqoption_profit_target_enabled", self.broker_config.get("profit_target_enabled", True)))
        self.profit_target_amount = target_val
        self.target_reached = False

        self.max_loss_enabled = bool(self.broker_config.get("iqoption_max_loss_enabled", self.broker_config.get("max_loss_enabled", True)))
        self.max_loss_amount = loss_val
        self.loss_limit_reached = False
        is_binary = (getattr(self, "iq_mode", "BINARY_OPTIONS") == "BINARY_OPTIONS")
        self.iqoption_risk_policy = IQOptionRiskPolicy(
            profit_target_amount=self.profit_target_amount,
            max_loss_amount=self.max_loss_amount,
            profit_target_enabled=self.profit_target_enabled,
            max_loss_enabled=self.max_loss_enabled,
            max_open_positions=1,
            zero_loss_blocks_entries=(self.execution_environment == "LIVE_REAL" and not is_binary),
        )

        self.feed = MultiAssetMarketFeed()
        self.agent = IntelligentTradingAgent()
        self.journal = TradeJournal()
        self.active_broker = "IQOPTION"
        iqoption_env = execution_environment or self.broker_config.get("iqoption_environment", "PAPER")
        iqoption_paper_init = float(self.broker_config.get("iqoption_paper_initial_balance", self.broker_config.get("iqoption_initial_balance", 10000.0)))
        if iqoption_paper_init <= 0.0:
            iqoption_paper_init = 10000.0

        # Arquitectura centrada en IQ Option — broker exclusivo
        self.broker_wallets: Dict[str, Dict[str, Any]] = {
            "IQOPTION": {
                "id": "IQOPTION",
                "name": "IQ Option",
                "icon": "📈",
                "category": "FOREX_CFD",
                "allowed_categories": ["FOREX", "CFD"],
                "environment": iqoption_env,
                "initial_balance": iqoption_paper_init,
                "cash": iqoption_paper_init,
                "profit_vault": 0.0,
                "target_amount": float(self.broker_config.get("iqoption_profit_target_amount", 50000.0)),
                "max_loss_amount": float(self.broker_config.get("iqoption_max_loss_amount", 0.0)),
                "target_reached": False,
                "loss_limit_reached": False,
                "is_running": True
            }
        }

        self.open_positions: Dict[str, Dict[str, Any]] = {}
        self.equity_history: List[Dict[str, Any]] = []
        self.last_exit_times: Dict[str, float] = {}
        self._broker_order_failure_cooldown: Dict[str, float] = {}

        # Sincronización exclusiva con IQ Option según entorno (Paper vs Real)
        if hasattr(self.feed, "iqoption"):
            if iqoption_env == "LIVE_REAL" and self.feed.iqoption.is_configured:
                iq_conn = self.feed.iqoption.connect()
                if iq_conn.get("connected"):
                    real_bal = float(iq_conn.get("balance", iqoption_paper_init))
                    self.broker_wallets["IQOPTION"]["cash"] = real_bal
                    self.broker_wallets["IQOPTION"]["initial_balance"] = real_bal
                    self.broker_wallets["IQOPTION"]["environment"] = "LIVE_REAL"
                else:
                    self.feed.iqoption.set_environment("PAPER")
                    self.broker_wallets["IQOPTION"]["environment"] = "PAPER"
            else:
                self.feed.iqoption.set_environment("PAPER")
                if self.broker_wallets["IQOPTION"]["cash"] <= 0.0:
                    self.broker_wallets["IQOPTION"]["cash"] = iqoption_paper_init
                    self.broker_wallets["IQOPTION"]["initial_balance"] = iqoption_paper_init

        # Si se especificó un saldo inicial explícito al instanciar (ej. en tests), respetarlo
        if initial_balance is not None:
            self.broker_wallets["IQOPTION"]["initial_balance"] = float(initial_balance)
            self.broker_wallets["IQOPTION"]["cash"] = float(initial_balance)
            self.broker_wallets["IQOPTION"]["profit_vault"] = 0.0

        # Asignar saldo activo según IQ Option (broker único exclusivo)
        active_wallet = self.broker_wallets["IQOPTION"]
        self.cash_balance = active_wallet["cash"]
        self.initial_balance = active_wallet["initial_balance"]
        self.execution_environment = active_wallet.get("environment", "PAPER")
        self.iqoption_risk_policy.zero_loss_blocks_entries = (
            self.execution_environment == "LIVE_REAL" and getattr(self, "iq_mode", "FOREX_CFD") != "BINARY_OPTIONS"
        )

        self._apply_iqoption_daily_halt()
        self.agent.update_learning_from_disk()
        self._record_equity_snapshot()

        # Motor especializado para Opciones Binarias Turbo de IQ Option
        iq_adapter = getattr(self.feed, "iqoption", None)
        self.binary_engine = BinaryOptionsStrategyEngine(
            iqoption_adapter=iq_adapter,
            journal=self.journal,
            learner=self.agent.learner if hasattr(self.agent, "learner") else None,
            initial_balance=self.cash_balance
        )



    def _sync_iqoption_open_positions(self, broker_positions: List[Dict[str, Any]]):
        """
        Sincroniza y reconcilia las posiciones de IQ Option de forma bidireccional y blindada.
        Garantiza que si el broker tiene al menos 1 posición abierta, esta se refleje en memoria
        bloqueando cualquier intento de abrir una segunda operación simultánea.
        Si el broker cerró la posición (Take-Profit, Stop-Loss o manual), se purga inmediatamente
        de la memoria y se registra en el journal, liberando el cupo al instante (0/1).
        """
        if len(broker_positions) > 1:
            self.broker_wallets["IQOPTION"]["is_running"] = False
            self.is_running = False
            self.agent._add_thought(
                f"🛑 BLOQUEO DE EXPOSICIÓN: IQ Option reportó {len(broker_positions)} posiciones. "
                "No se abrirán nuevas operaciones hasta intervención manual.",
                "WARNING",
                icon="🛑",
            )

        broker_active_ids = set()
        for bp in broker_positions:
            for k in ["id", "external_id", "internal_id"]:
                if bp.get(k):
                    broker_active_ids.add(str(bp[k]))
            for oid in bp.get("order_ids", []):
                broker_active_ids.add(str(oid))

        iq_memory_positions = [
            (pos_key, pos) for pos_key, pos in list(self.open_positions.items())
            if (pos.get("broker") == "IQOPTION" or pos.get("category") in ["FOREX", "OPTIONS", "CFD"])
        ]

        # 1. Si en el broker hay posiciones abiertas
        if len(broker_positions) > 0:
            self._zero_pos_counter = 0
            # Purgar si una posición en memoria ya no está en broker_active_ids
            for pos_key, pos in iq_memory_positions:
                pos_id = str(pos.get("broker_order_id", ""))
                ext_id = str(pos.get("position_id", ""))
                sym = pos.get("symbol", pos_key)
                if pos_id and pos_id not in broker_active_ids and ext_id not in broker_active_ids:
                    if pos_key in self.open_positions:
                        del self.open_positions[pos_key]
                    self.last_exit_times[sym] = time.time() + 180.0
                    cur_price = self.feed.assets.get(sym, {}).get("price", pos.get("current_price", pos.get("entry_price", 1.0)))
                    pnl = float(pos.get("current_pnl", 0.0))
                    inv = float(pos.get("invested_amount", 2000.0))
                    pnl_pct = round((pnl / inv) * 100, 2) if inv > 0 else 0.0
                    trade_record = {
                        "symbol": sym,
                        "name": pos.get("name", sym),
                        "broker": "IQOPTION",
                        "environment": self.broker_wallets.get("IQOPTION", {}).get("environment", "LIVE_REAL"),
                        "category": pos.get("category", "FOREX"),
                        "side": pos.get("side", "BUY_LONG"),
                        "quantity": pos.get("quantity", 1.0),
                        "entry_price": pos.get("entry_price", cur_price),
                        "exit_price": cur_price,
                        "invested_amount": inv,
                        "exit_value": round(inv + pnl, 2),
                        "pnl": pnl,
                        "pnl_percent": pnl_pct,
                        "entry_time": pos.get("entry_time", datetime.datetime.now().strftime("%H:%M:%S")),
                        "exit_time": datetime.datetime.now().strftime("%H:%M:%S"),
                        "reason": "Cierre confirmado en broker IQ Option (Take-Profit / Stop-Loss)",
                        "exit_reason": "Cierre confirmado en broker",
                        "exit_type": "BROKER_CLOSE",
                        "success": pnl >= 0
                    }
                    self.journal.record_trade(trade_record)
                    self.agent.record_trade_result(trade_record)
                    b_curr = getattr(self.feed.iqoption, "currency", "COP") if hasattr(self.feed, "iqoption") else "COP"
                    self.agent._add_thought(
                        f"💰 POSICIÓN CERRADA EN IQ OPTION: {sym} finalizó en el broker. Cupo liberado al instante (0/1).",
                        "TRADE_WIN" if pnl >= 0 else "TRADE_LOSS",
                        sym,
                        "💰"
                    )

            # Reconstruir o actualizar en memoria las posiciones que SÍ están activas en el broker
            for bp in broker_positions:
                act_id = bp.get("active_id")
                sym = bp.get("symbol") or ACTIVE_ID_TO_SYMBOL.get(int(act_id) if act_id is not None else 1, "EURUSD")
                pos_id = str(bp.get("id") or bp.get("external_id") or "")
                
                # Asignar clave: si sym está libre o pertenece a esta misma orden, usar sym. Si ya hay otra orden de sym, usar pos_key única.
                if sym not in self.open_positions:
                    pos_key = sym
                elif str(self.open_positions[sym].get("broker_order_id", "")) == pos_id or str(self.open_positions[sym].get("position_id", "")) == pos_id:
                    pos_key = sym
                else:
                    pos_key = f"{sym}_{pos_id}" if pos_id else f"{sym}_dup"

                entry_q = float(bp.get("open_quote", 0.0))
                asset_obj = self.feed.assets.get(sym, {})
                cur_p = asset_obj.get("price", entry_q) if entry_q > 0 else 1.0
                invested_amt = float(bp.get("invest") or 2000.0)
                pnl_net = float(bp.get("pnl_net", 0.0))
                pnl_pct = round((pnl_net / invested_amt) * 100, 2) if invested_amt > 0 else 0.0
                pos_side = bp.get("side", "BUY")
                pos_lev = bp.get("leverage", 500)

                if pos_key not in self.open_positions:
                    self.open_positions[pos_key] = {
                        "symbol": sym,
                        "name": asset_obj.get("name", sym),
                        "broker": "IQOPTION",
                        "category": "FOREX",
                        "side": pos_side,
                        "leverage": pos_lev,
                        "invested_amount": invested_amt,
                        "entry_price": entry_q if entry_q > 0 else cur_p,
                        "current_price": cur_p,
                        "quantity": 1.0,
                        "broker_order_id": str(bp.get("id", "")),
                        "position_id": str(bp.get("external_id") or bp.get("id", "")),
                        "current_pnl": pnl_net,
                        "current_pnl_percent": pnl_pct,
                        "entry_timestamp": time.time()
                    }
                else:
                    pos = self.open_positions[pos_key]
                    pos["symbol"] = sym
                    pos["current_pnl"] = pnl_net
                    pos["current_pnl_percent"] = pnl_pct
                    pos["side"] = pos_side
                    pos["leverage"] = pos_lev
                    if entry_q > 0:
                        pos["entry_price"] = entry_q
                    if bp.get("invest"):
                        pos["invested_amount"] = invested_amt

        # 2. Si el broker reporta cero posiciones abiertas, purgar con confirmación de 3 sondeos consecutivos
        elif len(broker_positions) == 0:
            if not hasattr(self, "_zero_pos_counter"):
                self._zero_pos_counter = 0
            self._zero_pos_counter += 1
            if self._zero_pos_counter >= 3:
                for pos_key, pos in iq_memory_positions:
                    sym = pos.get("symbol", pos_key)
                    if pos_key in self.open_positions:
                        del self.open_positions[pos_key]
                    self.last_exit_times[sym] = time.time() + 180.0
                    cur_price = self.feed.assets.get(sym, {}).get("price", pos.get("current_price", pos.get("entry_price", 1.0)))
                    pnl = float(pos.get("current_pnl", 0.0))
                    inv = float(pos.get("invested_amount", 2000.0))
                    pnl_pct = round((pnl / inv) * 100, 2) if inv > 0 else 0.0
                    trade_record = {
                        "symbol": sym,
                        "name": pos.get("name", sym),
                        "broker": "IQOPTION",
                        "environment": self.broker_wallets.get("IQOPTION", {}).get("environment", "LIVE_REAL"),
                        "category": pos.get("category", "FOREX"),
                        "side": pos.get("side", "BUY_LONG"),
                        "quantity": pos.get("quantity", 1.0),
                        "entry_price": pos.get("entry_price", cur_price),
                        "exit_price": cur_price,
                        "invested_amount": inv,
                        "exit_value": round(inv + pnl, 2),
                        "pnl": pnl,
                        "pnl_percent": pnl_pct,
                        "entry_time": pos.get("entry_time", datetime.datetime.now().strftime("%H:%M:%S")),
                        "exit_time": datetime.datetime.now().strftime("%H:%M:%S"),
                        "reason": "Cierre confirmado en broker IQ Option (Take-Profit / Stop-Loss)",
                        "exit_reason": "Cierre confirmado en broker",
                        "exit_type": "BROKER_CLOSE",
                        "success": pnl >= 0
                    }
                    self.journal.record_trade(trade_record)
                    self.agent.record_trade_result(trade_record)
                    b_curr = getattr(self.feed.iqoption, "currency", "COP") if hasattr(self.feed, "iqoption") else "COP"
                    self.agent._add_thought(
                        f"✅ OPERACIÓN CERRADA EN IQ OPTION: {sym} finalizó en el broker. Saldo y cupos 100% sincronizados.",
                        "INFO",
                        sym,
                        "📈"
                    )

        if hasattr(self, "risk_manager"):
            self.risk_manager.current_open_trades = len(self.open_positions)



    def set_execution_environment(self, env: str, custom_balance: Optional[float] = None, broker: Optional[str] = None) -> Dict[str, Any]:
        """Cambia el entorno de ejecución exclusivo de IQ Option (LIVE_REAL o PAPER)."""
        target_b = (broker or "IQOPTION").upper()
        if target_b != "IQOPTION":
            return {
                "success": False,
                "error": "PLATAFORMA_EXCLUSIVA_IQOPTION: solo IQ Option está permitido."
            }

        if env == "LIVE_REAL":
            if not hasattr(self.feed, "iqoption") or not self.feed.iqoption.is_configured:
                return {
                    "success": False,
                    "error": "Credenciales de IQ Option no configuradas. Por favor ingresa tu Correo Electrónico y Contraseña de IQ Option en la configuración."
                }
            self.feed.iqoption.set_environment("LIVE_REAL")
            conn = self.feed.iqoption.connect()
            if not conn.get("connected"):
                return {
                    "success": False,
                    "error": f"Error conectando a IQ Option: {conn.get('error', 'Credenciales inválidas')}. Se mantiene en Modo Demo/Paper."
                }
            self.broker_wallets["IQOPTION"]["environment"] = "LIVE_REAL"
            self.iqoption_risk_policy.zero_loss_blocks_entries = (getattr(self, "iq_mode", "FOREX_CFD") != "BINARY_OPTIONS")
            self.broker_config["iqoption_environment"] = "LIVE_REAL"
            real_bal = float(conn.get("real_balance") if conn.get("real_balance") is not None else conn.get("balance", 0.0))
            self.broker_wallets["IQOPTION"]["cash"] = real_bal
            self.broker_wallets["IQOPTION"]["initial_balance"] = real_bal
            self.broker_config["iqoption_real_initial_balance"] = real_bal
            self.broker_wallets["IQOPTION"]["profit_vault"] = self.get_broker_vault("IQOPTION", "LIVE_REAL")

            # LIMPIEZA DE POSICIONES SIMULADAS PREVIAS DE MODO PAPER:
            for s in list(self.open_positions.keys()):
                pos = self.open_positions[s]
                if pos.get("broker") == "IQOPTION":
                    del self.open_positions[s]

            self.execution_environment = "LIVE_REAL"
            self.cash_balance = self.broker_wallets["IQOPTION"]["cash"]
            self.initial_balance = self.broker_wallets["IQOPTION"]["initial_balance"]
            save_broker_config(self.broker_config)
            user_label = conn.get("name") or self.feed.iqoption.email or "Usuario Conectado"
            self.agent._add_thought(f"🔥 MODO DINERO REAL ACTIVADO en IQ Option ({user_label}). Saldo real en cuenta: ${real_bal:,.2f} USD.", "WARNING", icon="📈")
            return {"success": True, "broker": "IQOPTION", "environment": "LIVE_REAL", "equity": real_bal, "user": user_label}
        else:
            self.broker_wallets["IQOPTION"]["environment"] = "PAPER"
            self.iqoption_risk_policy.zero_loss_blocks_entries = False
            self.broker_config["iqoption_environment"] = "PAPER"
            if hasattr(self.feed, "iqoption"):
                self.feed.iqoption.set_environment("PAPER")
            if custom_balance is not None and float(custom_balance) > 0:
                bal_val = float(custom_balance)
                self.broker_wallets["IQOPTION"]["cash"] = bal_val
                self.broker_wallets["IQOPTION"]["initial_balance"] = bal_val
                self.broker_config["iqoption_paper_initial_balance"] = bal_val
            else:
                bal_val = 0.0
                if hasattr(self.feed, "iqoption") and self.feed.iqoption.connected and self.feed.iqoption.practice_balance_id:
                    self.feed.iqoption.change_balance(self.feed.iqoption.practice_balance_id)
                    bal_val = float(self.feed.iqoption.balance)
                
                # Si el broker reporta $0.0 en cuenta de práctica o no está conectado, asignar saldo demo saludable ($10,000 USD)
                if bal_val <= 0.0:
                    bal_val = float(self.broker_config.get("iqoption_paper_initial_balance", 10000.0))
                    if bal_val <= 0.0:
                        bal_val = 10000.0

                self.broker_wallets["IQOPTION"]["cash"] = bal_val
                self.broker_wallets["IQOPTION"]["initial_balance"] = bal_val
                self.broker_config["iqoption_paper_initial_balance"] = bal_val

            self.broker_wallets["IQOPTION"]["profit_vault"] = self.get_broker_vault("IQOPTION", "PAPER")
            self.execution_environment = "PAPER"
            self.cash_balance = self.broker_wallets["IQOPTION"]["cash"]
            self.initial_balance = self.broker_wallets["IQOPTION"]["initial_balance"]
            save_broker_config(self.broker_config)
            self.agent._add_thought(f"🛡️ MODO DEMO / PAPER ACTIVADO en IQ Option. Saldo de práctica: ${self.broker_wallets['IQOPTION']['cash']:,.2f} USD.", "INFO", icon="🛡️")
            return {"success": True, "broker": "IQOPTION", "environment": "PAPER", "equity": self.broker_wallets["IQOPTION"]["cash"]}

    def get_broker_vault(self, broker: str, env: Optional[str] = None) -> float:
        """
        Retorna el saldo de la bóveda estrictamente aislado por entorno (LIVE_REAL vs PAPER).
        Previene fugas de ganancias simuladas a la cuenta real y viceversa.
        """
        b = broker.upper()
        wallet = self.broker_wallets.get(b, {}) if hasattr(self, "broker_wallets") else {}
        current_env = env or wallet.get("environment", "PAPER")
        if current_env == "LIVE_REAL":
            return float(self.broker_config.get(f"{b.lower()}_real_profit_vault", 0.0))
        else:
            return float(self.broker_config.get(f"{b.lower()}_paper_profit_vault", self.broker_config.get(f"{b.lower()}_profit_vault", wallet.get("profit_vault", 0.0))))

    def save_broker_vault(self, broker: str, amount: float, env: Optional[str] = None):
        """
        Guarda el saldo de la bóveda en memoria y disco en su clave aislada por entorno.
        """
        b = broker.upper()
        amt = round(float(amount), 2)
        if hasattr(self, "broker_wallets") and b in self.broker_wallets:
            self.broker_wallets[b]["profit_vault"] = amt
        current_env = env or (self.broker_wallets.get(b, {}).get("environment", "PAPER") if hasattr(self, "broker_wallets") else "PAPER")
        if current_env == "LIVE_REAL":
            self.broker_config[f"{b.lower()}_real_profit_vault"] = amt
        else:
            self.broker_config[f"{b.lower()}_paper_profit_vault"] = amt
            self.broker_config[f"{b.lower()}_profit_vault"] = amt
        save_broker_config(self.broker_config)

    def get_broker_positions(self, broker: str) -> List[Dict[str, Any]]:
        b = broker.upper()
        return [
            p for p in self.open_positions.values()
            if (p.get("broker") or "IQOPTION").upper() == b
        ]

    def get_broker_cash(self, broker: str) -> float:
        b = broker.upper()
        if b in self.broker_wallets:
            return round(self.broker_wallets[b]["cash"], 2)
        return round(self.cash_balance, 2)

    def get_broker_equity(self, broker: str) -> float:
        b = broker.upper()
        wallet = self.broker_wallets.get(b)
        if not wallet:
            return round(self.get_total_equity(), 2)
        if wallet.get("environment") == "LIVE_REAL":
            open_pos = self.get_broker_positions(b)
            unrealized = sum(p.get("current_pnl", 0.0) for p in open_pos)
            invested = sum(p.get("invested_amount", 0.0) for p in open_pos)
            cash = wallet.get("cash", 0.0)
            return round(cash + invested + unrealized, 2)
        base = wallet.get("initial_balance", 0.0)
        vault = wallet.get("profit_vault", 0.0)
        unrealized = sum(p.get("current_pnl", 0.0) for p in self.get_broker_positions(b))
        return round(base + vault + unrealized, 2)

    def set_active_broker(self, broker: str) -> Dict[str, Any]:
        b = broker.upper()
        if b != "IQOPTION":
            return {
                "success": False,
                "error": "PLATAFORMA_EXCLUSIVA_IQOPTION: no se permiten brokers secundarios."
            }
        if b not in self.broker_wallets:
            return {"success": False, "error": f"Broker {broker} no soportado o no registrado"}

        self.active_broker = "IQOPTION"
        self.broker_config["active_broker"] = "IQOPTION"
        wallet = self.broker_wallets["IQOPTION"]
        self.operating_mode = "IQ_CFD"
        self.execution_environment = wallet.get("environment", "PAPER")

        wallet["profit_vault"] = self.get_broker_vault("IQOPTION", self.execution_environment)
        if "iqoption_initial_balance" in self.broker_config:
            wallet["initial_balance"] = float(self.broker_config["iqoption_initial_balance"])

        if self.execution_environment == "LIVE_REAL":
            if hasattr(self.feed, 'iqoption') and self.feed.iqoption.is_configured:
                acc = self.feed.iqoption.connect()
                if acc.get("connected"):
                    r_bal = float(acc.get("real_balance") if acc.get("real_balance") is not None else conn.get("balance", 0.0) if 'conn' in locals() else acc.get("balance", 0.0))
                    wallet["cash"] = r_bal
                    wallet["initial_balance"] = r_bal
        else:
            if hasattr(self.feed, 'iqoption') and self.feed.iqoption.is_configured and getattr(self.feed.iqoption, 'connected', False):
                p_bal = float(getattr(self.feed.iqoption, 'balance', 10000.0) or 10000.0)
                wallet["cash"] = p_bal
                wallet["initial_balance"] = p_bal

        self.cash_balance = wallet["cash"]
        self.initial_balance = wallet["initial_balance"]
        self.profit_target_amount = wallet.get("target_amount", self.profit_target_amount)
        self.max_loss_amount = wallet.get("max_loss_amount", self.max_loss_amount)

        self.feed.set_mode(self.operating_mode)
        self.broker_config["operating_mode"] = self.operating_mode
        save_broker_config(self.broker_config)
        
        self.agent._add_thought("🔀 Broker activo: 📈 IQ Option. Modo Forex CFD y métricas institucionales activadas.", "INFO", icon="📈")
        return {
            "success": True, 
            "active_broker": "IQOPTION", 
            "operating_mode": self.operating_mode,
            "cash": self.cash_balance,
            "equity": self.get_broker_equity("IQOPTION")
        }

    def set_operating_mode(self, mode: str):
        if mode == "IQ_BINARY":
            self.set_iq_mode("BINARY_OPTIONS")
        else:
            self.set_iq_mode("FOREX_CFD")

    def set_iq_mode(self, new_mode: str) -> Dict[str, Any]:
        """
        Conmuta entre MODO FOREX CFD y MODO OPCIONES BINARIAS con aislamiento absoluto:
        - FOREX_CFD: Opera con SL/TP dinámicos, trailing stop y apalancamiento sin expiración.
        - BINARY_OPTIONS: Opera con expiración fija (1m-5m), payout >= 80% y confluencia A+ (>=85%).
        """
        clean_m = new_mode.upper()
        if clean_m not in ["FOREX_CFD", "BINARY_OPTIONS"]:
            return {"success": False, "error": f"Modo inválido '{new_mode}'. Debe ser 'FOREX_CFD' o 'BINARY_OPTIONS'."}
        
        self.iq_mode = clean_m
        self.operating_mode = "IQ_CFD" if clean_m == "FOREX_CFD" else "IQ_BINARY"
        self.broker_config["iq_mode"] = clean_m
        self.broker_config["operating_mode"] = self.operating_mode
        if hasattr(self, "binary_engine"):
            self.binary_engine.iq = getattr(self.feed, "iqoption", None)

        if clean_m == "BINARY_OPTIONS":
            self.iqoption_risk_policy.zero_loss_blocks_entries = False
            self.agent._add_thought(
                "⏱️ MODO IQ OPTION CONMUTADO: OPCIONES BINARIAS TURBO (1m-5m). Aislamiento total de Forex CFD activo (Gatekeeper 1 operación, Payout >= 80%).",
                "SUCCESS",
                icon="⚡"
            )
        else:
            self.iqoption_risk_policy.zero_loss_blocks_entries = (self.execution_environment == "LIVE_REAL")
            self.agent._add_thought(
                "🌐 MODO IQ OPTION CONMUTADO: FOREX CFD TRADICIONAL. Aislamiento total de Binarias activo (SL/TP dinámico sin expiración).",
                "SUCCESS",
                icon="📈"
            )
        return {
            "success": True,
            "iq_mode": self.iq_mode,
            "operating_mode": self.operating_mode
        }

    def update_broker_keys(self, iqoption_email: str = "", iqoption_password: str = "", iqoption_ssid: str = "", **kwargs):
        """Actualiza exclusivamente las credenciales de IQ Option."""
        if iqoption_email or iqoption_password or iqoption_ssid:
            if "iqoption" not in self.broker_config:
                self.broker_config["iqoption"] = {}
            if iqoption_email:
                self.broker_config["iqoption"]["email"] = iqoption_email
            if iqoption_password:
                self.broker_config["iqoption"]["password"] = iqoption_password
            if iqoption_ssid is not None:
                self.broker_config["iqoption"]["ssid"] = iqoption_ssid
            self.broker_config["iqoption"]["enabled"] = bool(
                self.broker_config["iqoption"].get("ssid") or 
                (self.broker_config["iqoption"].get("email") and self.broker_config["iqoption"].get("password"))
            )
        save_broker_config(self.broker_config)
        self.feed.reload_credentials()

    def _record_equity_snapshot(self):
        total_equity = self.get_total_equity()
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        self.equity_history.append({
            "time": now_str,
            "equity": round(total_equity, 2),
            "cash": round(self.cash_balance, 2),
            "invested": round(self.get_invested_capital(), 2)
        })
        if len(self.equity_history) > 60:
            self.equity_history.pop(0)

    def get_invested_capital(self) -> float:
        return sum(pos["invested_amount"] for pos in self.open_positions.values())

    def get_unrealized_pnl(self) -> float:
        return sum(pos.get("current_pnl", 0.0) for pos in self.open_positions.values())

    def get_total_equity(self) -> float:
        active_wallet = self.broker_wallets.get(self.active_broker)
        if active_wallet:
            base = active_wallet.get("initial_balance", self.initial_balance)
            vault = active_wallet.get("profit_vault", 0.0)
            return round(base + vault, 2)
        return round(self.initial_balance, 2)

    def set_risk_limits(self, target_amount: float, max_loss: float, target_enabled: bool = True, loss_enabled: bool = True, broker: Optional[str] = None):
        target_b = (broker or self.active_broker).upper()
        target_val = max(0.0, float(target_amount))
        loss_val = max(0.0, float(max_loss))
        loss_enabled = bool(loss_enabled)

        if target_b in self.broker_wallets:
            self.broker_wallets[target_b]["target_amount"] = target_val
            self.broker_wallets[target_b]["max_loss_amount"] = loss_val
            self.broker_wallets[target_b]["max_loss_enabled"] = loss_enabled
            self.broker_wallets[target_b]["loss_limit_reached"] = False
            self.broker_wallets[target_b]["target_reached"] = False

        if target_b == self.active_broker:
            self.profit_target_amount = target_val
            self.profit_target_enabled = target_enabled
            self.target_reached = False

            self.max_loss_amount = loss_val
            self.max_loss_enabled = loss_enabled
            self.loss_limit_reached = False

        if target_b == "IQOPTION":
            self.iqoption_risk_policy.configure(
                profit_target_amount=target_val,
                max_loss_amount=loss_val,
                profit_target_enabled=target_enabled,
                max_loss_enabled=loss_enabled,
            )
            if getattr(self, "iq_mode", "FOREX_CFD") == "BINARY_OPTIONS":
                self.iqoption_risk_policy.zero_loss_blocks_entries = False
            self._apply_iqoption_daily_halt()

        # Persistir en disco para que nunca se reseteen al recargar la página o reiniciar
        self.broker_config["iqoption_profit_target_amount"] = target_val
        self.broker_config["iqoption_max_loss_amount"] = loss_val
        self.broker_config["iqoption_max_loss_enabled"] = loss_enabled
        self.broker_config["profit_target_enabled"] = target_enabled
        self.broker_config["max_loss_enabled"] = loss_enabled
        save_broker_config(self.broker_config)

        b_name = "IQ Option Forex CFD"
        if loss_enabled:
            msg_loss = "0 USD (Tolerancia Cero: Cero Pérdidas Permitidas)" if loss_val == 0.0 else f"-${loss_val:,.2f} USD"
        else:
            msg_loss = "Desactivado"

        self.agent._add_thought(
            f"⚙️ Parámetros de Riesgo Guardados ({b_name}): Meta: +${target_val:,.2f} | Límite Máx de Pérdida: {msg_loss}.",
            "INFO",
            icon="🛡️"
        )

    def clear_cooldown(self, symbol: Optional[str] = None):
        self.agent.learner.clear_cooldown(symbol)
        if symbol:
            self.last_exit_times.pop(symbol, None)
        else:
            self.last_exit_times.clear()
        if hasattr(self, "risk_manager"):
            self.risk_manager.clear_daily_losses(symbol)
        if hasattr(self.feed, "reset_forex_feed"):
            self.feed.reset_forex_feed()
        msg = f"Cooldown restaurado para {symbol}" if symbol else "Todos los cooldowns y cotizaciones han sido reiniciados."
        self.agent._add_thought(f"🔄 {msg}", "INFO", icon="✨")

    def step(self):
        if hasattr(self, "risk_manager"):
            self.risk_manager.current_open_trades = len(self.open_positions)
        market_state = self.feed.tick()

        if getattr(self, "iq_mode", "FOREX_CFD") == "BINARY_OPTIONS" and hasattr(self, "binary_engine"):
            cur_prices = {s: a.get("price", 1.0) for s, a in market_state.items()}
            bin_resolution = self.binary_engine.check_and_resolve_positions(cur_prices)
            if bin_resolution:
                invested = float(bin_resolution.get("amount", 0.0))
                pnl = float(bin_resolution.get("pnl", 0.0))
                exit_value = round(max(0.0, invested + pnl), 2)
                wallet = self.broker_wallets.get("IQOPTION", {})
                wallet["cash"] = round(wallet.get("cash", 0.0) + exit_value, 2)
                self.cash_balance = wallet["cash"]
                self.iqoption_risk_policy.record_closed_trade(pnl)
                self._apply_iqoption_daily_halt()
                res_type = bin_resolution.get("result", "WIN")
                res_icon = "🏆" if res_type == "WIN" else ("🤝" if res_type == "TIE" else "🛡️")
                self.agent._add_thought(
                    f"{res_icon} {bin_resolution['reason']}",
                    "SUCCESS" if res_type == "WIN" else "INFO",
                    bin_resolution.get("symbol"),
                    res_icon
                )

        # 1. Actualizar posiciones abiertas y gestionar Trailing Stop Adaptativo
        for pos_key, pos in list(self.open_positions.items()):
            sym = pos.get("symbol", pos_key)
            asset = market_state.get(sym)
            if not asset:
                continue
            current_price = asset["price"]
            entry_price = pos["entry_price"]
            quantity = pos["quantity"]
            category = asset.get("category", "TRADFI_STOCK")
            
            if category == "FOREX" or pos.get("broker") == "IQOPTION":
                pos["current_price"] = current_price
                leverage = float(pos.get("leverage", 500))
                inv = float(pos.get("invested_amount", 0.0))
                side = str(pos.get("side", "BUY")).upper()
                if entry_price > 0 and inv > 0:
                    diff = (current_price - entry_price) if side in ["BUY", "BUY_LONG", "CALL"] else (entry_price - current_price)
                    # Fórmula institucional exacta de IQ Option para Margen Forex CFD:
                    live_pnl = round(inv * (diff / entry_price) * leverage, 2)
                    pos["current_pnl"] = live_pnl
                    pos["current_value"] = round(max(0.0, inv + live_pnl), 2)
                    pos["current_pnl_percent"] = round((live_pnl / inv) * 100, 2)
                else:
                    pos["current_value"] = round(inv + pos.get("current_pnl", 0.0), 2)
                pnl_pct = pos.get("current_pnl_percent", 0.0)
            else:
                current_value = quantity * current_price
                pnl = current_value - pos["invested_amount"]
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
                
                pos["current_price"] = current_price
                pos["current_value"] = round(current_value, 2)
                pos["current_pnl"] = round(pnl, 2)
                pos["current_pnl_percent"] = round(pnl_pct, 2)

            pos["highest_price"] = max(pos.get("highest_price", entry_price), current_price)
            entry_ts = pos.get("entry_timestamp", 0)
            elapsed = time.time() - entry_ts if entry_ts > 0 else 999

            # TRAILING STOP & BREAK-EVEN DINÁMICO FOREX CFD IQ OPTION:
            # Protege ganancias progresivamente con holgura dinámica y asegura Cero Pérdidas (Riesgo Cero).
            side = str(pos.get("side", "BUY_LONG")).upper()
            is_long = side in ["BUY", "BUY_LONG", "CALL"]
            
            # 1. Break-Even Protector ultra-rápido: Al alcanzar +0.25% de ganancia tras 15 segundos,
            # asegura el precio de entrada + spread para garantizar CERO PÉRDIDAS.
            if pnl_pct >= 0.25 and elapsed >= 15.0:
                be_sl = round(entry_price * 1.0003, 5) if is_long else round(entry_price * 0.9997, 5)
                if (is_long and pos.get("stop_loss", 0) < be_sl) or (not is_long and (pos.get("stop_loss", 999999) > be_sl or pos.get("stop_loss", 0) == 0)):
                    pos["stop_loss"] = be_sl
                    self.agent._add_thought(f"🛡️ Break-Even Blindado en {sym}: Stop-Loss elevado a ${be_sl:,.5f} (Riesgo Cero / Cero Pérdidas).", "INFO", sym, "🛡️")

            # 2. Locking Profit: Al superar +0.60% de retorno, asegura al menos +0.25% neto
            if pnl_pct >= 0.60:
                lock_sl = round(entry_price * 1.0025, 5) if is_long else round(entry_price * 0.9975, 5)
                if (is_long and pos.get("stop_loss", 0) < lock_sl) or (not is_long and pos.get("stop_loss", 999999) > lock_sl):
                    pos["stop_loss"] = lock_sl
                    self.agent._add_thought(f"🔒 Bloqueo de Ganancia en {sym}: Beneficio mínimo asegurado en ${lock_sl:,.5f}.", "INFO", sym, "🔒")

            # 3. Trailing Stop Dinámico: Persigue máximos con holgura para maximizar ganancias
            if pnl_pct >= 1.20:
                high_p = pos.get("highest_price", entry_price)
                trail_sl = round(high_p * 0.997, 5) if is_long else round(pos.get("lowest_price", entry_price) * 1.003, 5)
                if (is_long and pos.get("stop_loss", 0) < trail_sl) or (not is_long and pos.get("stop_loss", 999999) > trail_sl):
                    pos["stop_loss"] = trail_sl
                    self.agent._add_thought(f"🚀 Trailing Stop Forex en {sym}: Persiguiendo pico, Stop asegurado en ${trail_sl:,.5f}.", "INFO", sym, "🚀")
            
            tp = pos.get("take_profit", entry_price * 1.04)
            if tp > entry_price:
                pct_to_tp = min(100.0, max(0.0, ((current_price - entry_price) / (tp - entry_price)) * 100))
            else:
                pct_to_tp = 0.0
            pos["progress_to_target"] = round(pct_to_tp, 1)

        # 2 & 3. CIRCUIT BREAKERS PARA IQ OPTION
        for b_id, b_wal in list(self.broker_wallets.items()):
            b_equity = self.get_broker_equity(b_id)
            b_init_bal = b_wal.get("initial_balance", 100.0)
            b_profit = round(b_equity - b_init_bal, 2)

            # Meta de ganancia
            b_target_amt = b_wal.get("target_amount", self.profit_target_amount)
            b_curr = "COP" if (b_id == "IQOPTION" and getattr(self.feed.iqoption, "currency", "USD") == "COP") else "USD"
            if self.profit_target_enabled and b_profit >= b_target_amt and not b_wal.get("target_alerted", False):
                b_wal["target_alerted"] = True
                self.agent._add_thought(
                    f"🏆 ¡OBJETIVO DE GANANCIA ALCANZADO [📈 IQ Option] (+{b_curr} {b_profit:,.2f})! "
                    f"Saldo total disponible en cuenta: {b_curr} {b_equity:,.2f}. El motor continúa operando con disciplina matemática.",
                    "TRADE_WIN",
                    icon="🎯"
                )

            # Límite defensivo de pérdida
            b_max_loss = b_wal.get("max_loss_amount", self.max_loss_amount)
            b_loss_enabled = b_wal.get("max_loss_enabled", b_wal.get("loss_enabled", self.max_loss_enabled))
            
            is_b_loss_triggered = False
            if b_loss_enabled and b_max_loss > 0.0 and not b_wal.get("loss_limit_reached", False):
                if b_profit <= -b_max_loss:
                    is_b_loss_triggered = True

            if is_b_loss_triggered:
                b_wal["loss_limit_reached"] = True
                self.loss_limit_reached = True
                # Cierra posiciones para proteger capital
                for sym in list(self.open_positions.keys()):
                    asset = self.feed.get_asset(sym)
                    if asset:
                        decision = {"decision": "EMERGENCY_SELL", "reason_simple": f"Escudo Defensivo [IQ Option]: Límite de Pérdida (-${b_max_loss:,.2f}) alcanzado"}
                        self._execute_sell(sym, asset, decision)
                self.agent._add_thought(
                    f"🛡️ ESCUDO ACTIVADO [📈 IQ Option]: Límite de pérdida alcanzado (${b_profit:,.2f} USD). "
                    f"Operaciones detenidas para blindar capital base en ${b_wal['initial_balance']:,.2f} USD.",
                    "WARNING",
                    icon="🛡️"
                )

        # 4. Sincronización continua con IQ Option en segundo plano
        if not hasattr(self, "_last_broker_sync"):
            self._last_broker_sync = {}

        now_sync = time.time()
        b_wal = self.broker_wallets.get("IQOPTION", {})
        if b_wal.get("environment") == "LIVE_REAL":
            if hasattr(self.feed, 'iqoption') and self.feed.iqoption.is_configured:
                if (now_sync - self._last_broker_sync.get("IQOPTION", 0.0)) > 4.0:
                    self._last_broker_sync["IQOPTION"] = now_sync
                    acc = self.feed.iqoption.get_account_balances()
                    if acc.get("authenticated"):
                        r_bal = float(acc.get("real_balance", 0.0))
                        if r_bal > 0:
                            b_wal["cash"] = r_bal
                            if b_wal.get("initial_balance", 0.0) <= 0.0:
                                b_wal["initial_balance"] = r_bal
                            self.cash_balance = b_wal["cash"]
                            if self.initial_balance <= 0.0:
                                self.initial_balance = b_wal["initial_balance"]
                        if acc.get("positions_synced"):
                            broker_positions = acc.get("open_positions", [])
                            self._sync_iqoption_open_positions(broker_positions)

        # 5. Escaneo y Operación Autónoma Continua 24/7
        if self.is_running:
            self._evaluate_and_trade(market_state)

        # 6. Snapshot de equity
        self._record_equity_snapshot()

    def _apply_iqoption_daily_halt(self):
        """Detiene nuevas entradas tras alcanzar meta o límite diario realizado."""
        snapshot = self.iqoption_risk_policy.snapshot()
        wallet = self.broker_wallets.get("IQOPTION", {})
        wallet["target_reached"] = snapshot["halted_reason"] == "META_DIARIA_ALCANZADA"
        wallet["loss_limit_reached"] = snapshot["halted_reason"] == "LIMITE_PERDIDA_DIARIA_ALCANZADO"
        
        is_binary = (getattr(self, "iq_mode", "FOREX_CFD") == "BINARY_OPTIONS")
        if snapshot["halted"]:
            # En Opciones Binarias Turbo, la tolerancia cero de Forex CFD no detiene el motor
            if is_binary and snapshot["halted_reason"] == "TOLERANCIA_CERO_BLOQUEA_NUEVAS_ENTRADAS":
                return
            wallet["is_running"] = False
            self.target_reached = wallet["target_reached"]
            self.loss_limit_reached = wallet["loss_limit_reached"]

    def _iqoption_can_open(self) -> bool:
        active_count = len(self.get_broker_positions("IQOPTION"))
        if hasattr(self, "binary_engine") and self.binary_engine.has_active_position:
            active_count += 1
            
        is_binary = (getattr(self, "iq_mode", "FOREX_CFD") == "BINARY_OPTIONS")
        if is_binary:
            # Gatekeeper estricto 0/1: solo 1 operación a la vez
            if active_count >= 1 or self._iqoption_order_pending:
                return False
            snapshot = self.iqoption_risk_policy.snapshot()
            if snapshot.get("halted_reason") in ["META_DIARIA_ALCANZADA", "LIMITE_PERDIDA_DIARIA_ALCANZADO"]:
                return False
            return True

        decision = self.iqoption_risk_policy.can_open(
            active_positions=active_count,
            pending_order=self._iqoption_order_pending,
        )
        self._apply_iqoption_daily_halt()

        if not decision.allowed:
            self.agent._add_thought(
                f"🛡️ IQ Option: nueva entrada bloqueada ({decision.reason}).",
                "WARNING",
                icon="🛡️",
            )
        return decision.allowed

    def _evaluate_and_trade(self, market_state: Dict[str, Any]):
        # A. Evaluar salidas de posiciones abiertas para TODOS los brokers (incluyendo CFDs existentes)
        for sym, pos in list(self.open_positions.items()):
            pos_b = (pos.get("broker") or "IQOPTION").upper()
            pos_wal = self.broker_wallets.get(pos_b, {})
            if pos.get("execution_state") == "PENDING_CLOSE_RECONCILIATION":
                continue
            if not pos_wal.get("is_running", True):
                continue
            asset = market_state.get(sym)
            if not asset:
                continue
            entry_ts = pos.get("entry_timestamp", 0)
            elapsed = time.time() - entry_ts if entry_ts > 0 else 999

            # GESTIÓN EXCLUSIVA IQ OPTION: FOREX CFD CON STOP-LOSS Y TAKE-PROFIT AUTOMÁTICOS
            if pos_b == "IQOPTION":
                decision_data = self.agent.evaluate_asset(asset, self.open_positions)
                pos_side = pos.get("side", "BUY_LONG").upper()
                cur_price = asset["price"]
                entry_p = pos.get("entry_price", cur_price)
                initial_sl = pos.get("initial_stop_loss", pos.get("stop_loss", entry_p))
                risk_r = abs(entry_p - initial_sl) if abs(entry_p - initial_sl) > 0 else (entry_p * 0.005)

                # Dynamic Break-Even & Trailing Stop:
                if pos_side in ["BUY", "BUY_LONG", "CALL"]:
                    favorable_dist = cur_price - entry_p
                    if favorable_dist >= risk_r and not pos.get("is_break_even"):
                        pos["stop_loss"] = entry_p
                        pos["is_break_even"] = True
                        self.agent._add_thought(f"🛡️ Break-Even Activado en {sym}: Stop-Loss ajustado a precio de entrada ({entry_p}) para blindar la operación a CERO RIESGO.", "INFO", sym, "🛡️")
                    elif favorable_dist >= 1.5 * risk_r:
                        trail_sl = round(entry_p + 0.5 * risk_r, 4)
                        if trail_sl > pos.get("stop_loss", 0):
                            pos["stop_loss"] = trail_sl
                    is_hard_sl = cur_price <= pos.get("stop_loss", 0)
                    is_hard_tp = cur_price >= pos.get("take_profit", 999999)
                else:
                    favorable_dist = entry_p - cur_price
                    if favorable_dist >= risk_r and not pos.get("is_break_even"):
                        pos["stop_loss"] = entry_p
                        pos["is_break_even"] = True
                        self.agent._add_thought(f"🛡️ Break-Even Activado en {sym}: Stop-Loss ajustado a precio de entrada ({entry_p}) para blindar la operación a CERO RIESGO.", "INFO", sym, "🛡️")
                    elif favorable_dist >= 1.5 * risk_r:
                        trail_sl = round(entry_p - 0.5 * risk_r, 4)
                        if trail_sl < pos.get("stop_loss", 999999):
                            pos["stop_loss"] = trail_sl
                    is_hard_sl = cur_price >= pos.get("stop_loss", 999999)
                    is_hard_tp = cur_price <= pos.get("take_profit", 0)

                # Margen mínimo de 10s para maduración de la posición
                if elapsed < 10.0 and not is_hard_sl and not is_hard_tp:
                    continue

                if is_hard_tp:
                    self._execute_sell(sym, asset, {"decision": "SELL_TAKE_PROFIT", "reason_simple": f"🎯 Take-Profit alcanzado en {sym}: Objetivo de beneficio cumplido."})
                    continue
                elif is_hard_sl:
                    self._execute_sell(sym, asset, {"decision": "SELL_STOP_LOSS", "reason_simple": f"🛡️ Stop-Loss defensivo en {sym}: Preservando capital."})
                    continue
                elif decision_data.get("decision") in ["SELL", "PUT"] and pos_side in ["BUY", "BUY_LONG", "CALL"] and decision_data.get("confidence", 0) >= 85:
                    self._execute_sell(sym, asset, {"decision": "SELL_REVERSAL", "reason_simple": f"⚡ Reversión técnica en {sym}: Asegurando rendimiento."})
                    continue
                elif decision_data.get("decision") in ["BUY", "CALL"] and pos_side in ["SELL", "PUT"] and decision_data.get("confidence", 0) >= 85:
                    self._execute_sell(sym, asset, {"decision": "SELL_REVERSAL", "reason_simple": f"⚡ Reversión técnica en {sym}: Asegurando rendimiento."})
                    continue
            else:
                cur_price = asset["price"]
                pos_side = pos.get("side", "BUY_LONG").upper()
                if pos_side in ["BUY", "BUY_LONG"]:
                    is_hard_sl = cur_price <= pos.get("stop_loss", 0)
                    is_hard_tp = cur_price >= pos.get("take_profit", 999999)
                else:
                    is_hard_sl = cur_price >= pos.get("stop_loss", 999999)
                    is_hard_tp = cur_price <= pos.get("take_profit", 0)
                if is_hard_sl:
                    self._execute_sell(sym, asset, {"decision": "SELL_STOP_LOSS", "reason_simple": f"Stop Loss en {sym}"})
                    continue
                elif is_hard_tp:
                    self._execute_sell(sym, asset, {"decision": "SELL_TAKE_PROFIT", "reason_simple": f"Take Profit en {sym}"})
                    continue

        now_ts = time.time()
        is_weekend = datetime.datetime.now(datetime.timezone.utc).weekday() >= 5

        # B. Evaluar NUEVAS ENTRADAS
        # Si el modo activo de IQ Option es BINARY_OPTIONS, delegar la apertura de NUEVAS entradas a binarias
        if self.active_broker == "IQOPTION" and getattr(self, "iq_mode", "FOREX_CFD") == "BINARY_OPTIONS":
            self._evaluate_and_trade_binary(market_state)
            return

        for b_id, wallet in list(self.broker_wallets.items()):
            # Enfoque exclusivo en IQ Option: si el broker activo es IQOPTION y hay activos de Forex, concentrar el 100% en IQ Option
            if self.active_broker == "IQOPTION" and b_id != "IQOPTION":
                has_iq_assets = any(asset.get("category") == "FOREX" or "-OTC" in s for s, asset in market_state.items())
                if has_iq_assets:
                    continue
            if not wallet.get("is_running", True):
                continue
            if wallet.get("target_reached") or wallet.get("loss_limit_reached"):
                continue

            is_cop = (b_id == "IQOPTION" and getattr(self.feed.iqoption, "currency", "USD") == "COP")
            min_cash = 2000.0 if is_cop else 1.0

            allowed_categories = wallet.get("allowed_categories", ["FOREX", "OPTIONS", "CFD"])
            # Límite estricto de exposición: máximo 1 sola posición activa a la vez
            max_positions = 1
            broker_positions = self.get_broker_positions(b_id)

            if len(broker_positions) >= max_positions or wallet.get("cash", 0.0) < min_cash:
                continue

            # Pausa de enfriamiento preventiva si hubo un fallo reciente de orden en este broker
            if time.time() < self._broker_order_failure_cooldown.get(b_id, 0.0):
                continue

            candidates = []
            for sym, asset in market_state.items():
                if sym in self.open_positions:
                    continue
                # Blindaje contra duplicados de activo subyacente (ej: evitar abrir EURUSD y EURUSD-OTC a la vez)
                clean_underlying = sym.replace("-OTC", "").replace("OTC", "")
                existing_underlyings = [p_sym.replace("-OTC", "").replace("OTC", "") for p_sym in self.open_positions.keys()]
                if clean_underlying in existing_underlyings:
                    continue
                if allowed_categories and asset.get("category") not in allowed_categories:
                    continue
                
                # En IQ Option Margen CFD, se operan exclusivamente los pares Forex estándar (EURUSD, GBPUSD, etc.) y Acciones.
                # Se excluyen pares OTC porque en IQ Option los OTC corresponden a opciones binarias/blitz.
                if b_id == "IQOPTION" and ("-OTC" in sym or "OTC" in sym):
                    continue

                # MODELO EXCLUSIVO IQ OPTION: FOREX TRADICIONAL CFD
                if b_id == "IQOPTION":
                    op_trade_type = "CFD"
                else:
                    op_trade_type = "SPOT"
                
                # Descartar activos en enfriamiento del agente o en enfriamiento post-salida reciente (120s en Forex CFD, 180s en spot)
                cooldown_dur = 120.0 if b_id == "IQOPTION" else 180.0
                if self.agent.learner.is_asset_in_cooldown(sym):
                    continue
                if (time.time() - self.last_exit_times.get(sym, 0)) < cooldown_dur:
                    continue

                decision_data = self.agent.evaluate_asset(asset, self.open_positions)
                is_buy = (decision_data["decision"] == "BUY" and decision_data["confidence"] >= 80)
                is_put = (b_id == "IQOPTION" and decision_data["decision"] in ["SELL", "PUT"] and decision_data["confidence"] >= 80)

                if (is_buy or is_put):
                    volatility_weight = asset.get("volatility", 0.005) * 1000
                    exp_boost = self.agent.learner.get_asset_confidence_boost(sym)
                    priority_score = decision_data["confidence"] * exp_boost * (1.0 + volatility_weight * 0.5)
                    decision_data["op_trade_type"] = op_trade_type
                    candidates.append((priority_score, sym, asset, decision_data))

            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                best_score, best_sym, best_asset, best_decision = candidates[0]
                self._execute_buy(best_sym, best_asset, best_decision, broker_id=b_id)

    def _evaluate_and_trade_binary(self, market_state: Dict[str, Any]):
        """
        Lógica 100% aislada para Opciones Binarias Turbo / Blitz:
        - Gatekeeper estricto: máximo 1 sola posición activa a la vez.
        - Filtro matemático de Payout >= 80%.
        - Confluencia A+ (confianza >= 85%) con análisis de mecha y RSI.
        - Cooldown forzado de 180s en el activo tras cierre.
        """
        if not hasattr(self, "binary_engine"):
            return

        # Gatekeeper único compartido por binarias y CFD.
        if not self._iqoption_can_open():
            return

        wallet = self.broker_wallets.get("IQOPTION", {})
        if not wallet.get("is_running", True):
            return

        is_cop = (getattr(self.feed.iqoption, "currency", "USD") == "COP")
        min_cash = 2000.0 if is_cop else 1.0
        cash = wallet.get("cash", 0.0)
        if cash < min_cash:
            return

        trade_amount = 2000.0 if is_cop else 2.0

        candidates = []
        scanned_evals = []
        for sym, asset in market_state.items():
            cat = asset.get("category")
            # Permitir Forex tradicional y pares OTC 24/7 para Opciones Binarias
            if cat not in ["FOREX", "OPTIONS", "CFD"] and "-OTC" not in sym:
                continue

            candles = getattr(self.feed, "candles", {}).get(sym, [])
            eval_res = self.binary_engine.evaluate_asset(asset, candles)
            dec = eval_res.get("decision")
            conf = eval_res.get("confidence", 0)
            scanned_evals.append((conf, sym, dec, eval_res))

            if dec in ["CALL", "PUT"] and conf >= self.binary_engine.min_confidence:
                payout = eval_res.get("payout", 0.85)
                score = conf * payout
                candidates.append((score, sym, dec, asset, eval_res))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            best_score, best_sym, best_dir, best_asset, best_eval = candidates[0]
            price = best_asset.get("price", 1.0)
            order_res = self.binary_engine.execute_binary_option(
                symbol=best_sym,
                direction=best_dir,
                amount=trade_amount,
                duration_minutes=1,
                entry_price=price
            )
            if order_res.get("success"):
                wallet["cash"] = round(wallet.get("cash", 0.0) - trade_amount, 2)
                self.cash_balance = wallet["cash"]
                real_oid = order_res.get("order_id", "EN_CURSO")
                self.agent._add_thought(
                    f"🎯 OPCIÓN BINARIA LANZADA [IQ OPTION]: {best_sym} {best_dir} (${trade_amount:,.2f}) | Expiración 60s | ID #{real_oid} | {best_eval['reason']}",
                    "SUCCESS",
                    best_sym,
                    "🎯"
                )
            else:
                self.agent._add_thought(
                    f"⚠️ Orden Binaria {best_sym} {best_dir} no concretada: {order_res.get('error', 'Rechazada por el broker')}",
                    "WARNING",
                    best_sym,
                    "⚠️"
                )
        else:
            # Heartbeat informativo para el Dashboard cada 8-10 segundos
            now_scan = time.time()
            if not hasattr(self, "_last_binary_scan_ts"):
                self._last_binary_scan_ts = 0.0
            if (now_scan - self._last_binary_scan_ts) >= 10.0:
                self._last_binary_scan_ts = now_scan
                if scanned_evals:
                    scanned_evals.sort(key=lambda x: x[0], reverse=True)
                    top_conf, top_sym, top_dec, top_res = scanned_evals[0]
                    self.agent._add_thought(
                        f"⏱️ [Binarias Turbo] Escaneando {len(scanned_evals)} pares en vivo. Mejor activo: {top_sym} ({top_dec} {top_conf}% - Req: >= {self.binary_engine.min_confidence}%). Cartera 0/1 disponible.",
                        "INFO",
                        top_sym,
                        "⏱️"
                    )

    def trigger_test_binary_trade(
        self, 
        symbol: str = "EURJPY", 
        direction: str = "CALL", 
        amount: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Dispara una orden de prueba controlada de Binarias Turbo directamente en IQ Option.
        Respeta al 100% el límite inquebrantable de 1 sola operación a la vez (0/1).
        """
        if not hasattr(self, "binary_engine"):
            return {"success": False, "error": "Motor de opciones binarias no inicializado."}

        if self.binary_engine.has_active_position:
            return {
                "success": False, 
                "error": "GATEKEEPER ACTIVO: Ya existe 1 operación binaria en curso (1/1 ocupado). Espere su resolución."
            }

        active_count = len(self.get_broker_positions("IQOPTION"))
        if hasattr(self, "binary_engine") and self.binary_engine.has_active_position:
            active_count += 1
        if active_count >= 1 or self._iqoption_order_pending:
            return {
                "success": False,
                "error": "GATEKEEPER ACTIVO: Ya existe 1 operación en curso (1/1 ocupado). Espere su resolución."
            }

        wallet = self.broker_wallets.get("IQOPTION", {})
        is_cop = (getattr(self.feed.iqoption, "currency", "USD") == "COP")
        min_amount = 2000.0 if is_cop else 1.0
        final_amount = float(amount) if amount and float(amount) >= min_amount else min_amount

        cash = wallet.get("cash", 0.0)
        if cash < final_amount:
            return {
                "success": False,
                "error": f"Saldo insuficiente: Dispones de {cash:,.2f} y se requieren al menos {final_amount:,.2f}."
            }

        res = self.binary_engine.trigger_test_binary_trade(
            symbol=symbol,
            direction=direction,
            amount=final_amount,
            duration_minutes=1
        )
        if res.get("success"):
            wallet["cash"] = round(wallet.get("cash", 0.0) - final_amount, 2)
            self.cash_balance = wallet["cash"]
            oid = res.get("order_id", "REGISTRADA")
            self.agent._add_thought(
                f"🧪 PRUEBA BINARIA EN PRODUCCIÓN: {symbol} {direction} (${final_amount:,.2f}) | Orden Oficial #{oid} en IQ Option | 1/1 Ocupado",
                "SUCCESS",
                symbol,
                "🧪"
            )
        else:
            self.agent._add_thought(
                f"⚠️ Error en prueba binaria {symbol}: {res.get('error', 'Rechazada por el broker')}",
                "WARNING",
                symbol,
                "⚠️"
            )

        return res


    def _execute_buy(self, symbol: str, asset: Dict[str, Any], decision_data: Dict[str, Any], broker_id: Optional[str] = None):
        broker_id = "IQOPTION"
        wallet = self.broker_wallets.get("IQOPTION", {})
        category = "FOREX"
        
        # Operación directa con el efectivo de la cuenta
        available_cash = max(0.0, float(wallet.get("cash", 0.0)))
        is_broker_live = (wallet.get("environment") == "LIVE_REAL")
        is_cop = (getattr(self.feed.iqoption, "currency", "USD") == "COP") if hasattr(self.feed, 'iqoption') else False
        kelly_pct = decision_data.get("budget_percent", 20.0)
        effective_pct = min(kelly_pct, 25.0)

        min_trade = 2000.0 if is_cop else 1.0

        if is_cop:
            target_amount = 2000.0
            actual_investment = 2000.0
        else:
            if available_cash <= 35.0:
                target_amount = min_trade
            elif available_cash <= 500.0:
                target_amount = round(max(min_trade, available_cash * (effective_pct / 100.0)), 2)
            else:
                target_amount = round(max(min_trade, min(available_cash * 0.05, 5000.0)), 2)
            actual_investment = target_amount

        if actual_investment < min_trade or actual_investment > available_cash:
            return

        # CONTROL ESTRICTO DE CUPOS: CFD y binarias comparten una sola posición global.
        if not self._iqoption_can_open():
            return
        forex_open = [p for p in self.open_positions.values() if p.get("broker") == "IQOPTION" or p.get("category") == "FOREX"]
        if len(forex_open) >= 1 or (hasattr(self, "binary_engine") and self.binary_engine.has_active_position):
            return
        if hasattr(self.feed, "iqoption"):
            b_open = self.feed.iqoption.get_open_positions()
            if len(b_open) >= 1:
                return
        now_t = time.time()
        if hasattr(self, "_last_iqoption_trade_time") and (now_t - getattr(self, "_last_iqoption_trade_time", 0.0) < 120.0):
            return
        self._last_iqoption_trade_time = now_t
        # Enfriamiento forzado de 15 minutos en este símbolo para obligar a rotar a otros pares
        self.last_exit_times[symbol] = now_t + 900.0

        price = asset["price"]
        quantity = round(actual_investment / price, 4) if price > 0 else 1.0

        # Verificación de gestión de riesgo institucional
        equity_now = self.get_broker_equity("IQOPTION")
        if hasattr(self, "risk_manager"):
            b_max_loss = wallet.get("max_loss_amount", self.max_loss_amount)
            b_loss_enabled = wallet.get("max_loss_enabled", self.max_loss_enabled)
            if not self.risk_manager.can_open_trade(
                risk_amount=actual_investment * 0.02,
                current_equity=equity_now,
                is_margin_account=True,
                is_tradfi=False,
                broker_id="IQOPTION",
                broker_initial_balance=wallet.get("initial_balance", equity_now),
                max_loss_amount=b_max_loss,
                max_loss_enabled=b_loss_enabled,
                current_open_count=len(self.open_positions)
            ):
                self.agent._add_thought(f"🛡️ Gestión de riesgo: Entrada en {symbol} pausada por límites operativos.", "INFO", symbol, "🛡️")
                return

        stop_loss = decision_data.get("stop_loss", round(price * 0.975, 4))
        take_profit = decision_data.get("take_profit", round(price * 1.045, 4))

        position = {
            "symbol": symbol,
            "name": asset.get("name", symbol),
            "broker": "IQOPTION",
            "category": "FOREX",
            "type": asset.get("type", "Forex CFD"),
            "icon": asset.get("icon", "📈"),
            "entry_price": price,
            "current_price": price,
            "quantity": quantity,
            "invested_amount": actual_investment,
            "current_value": actual_investment,
            "stop_loss": stop_loss,
            "initial_stop_loss": stop_loss,
            "highest_price": price,
            "take_profit": take_profit,
            "side": "PUT" if ("SELL" in str(decision_data.get("decision", "")) or "PUT" in str(decision_data.get("action_type", "")) or "BAJISTA" in str(decision_data.get("action_type", ""))) else "CALL",
            "is_cfd": True,
            "trade_type": "CFD",
            "duration_sec": 0,
            "entry_time": datetime.datetime.now().strftime("%H:%M:%S"),
            "entry_timestamp": time.time(),
            "entry_confidence": decision_data["confidence"],
            "reason": decision_data["reason_simple"],
            "current_pnl": 0.0,
            "current_pnl_percent": 0.0,
            "progress_to_target": 0.0
        }

        # Enrutamiento de orden en IQ Option (Paper o Real) - Forex CFD
        if hasattr(self.feed, "iqoption"):
            pos_side = position.get("side", "BUY_LONG")
            cfd_side = "sell" if pos_side in ["PUT", "SELL", "SELL_SHORT"] else "buy"
            sl_pct = 95.0
            tp_pct = 200.0
            if price > 0 and stop_loss > 0 and take_profit > 0:
                sl_pct = round(abs(price - stop_loss) / price * 100, 2)
                tp_pct = round(abs(take_profit - price) / price * 100, 2)
            self._iqoption_order_pending = True
            try:
                iq_res = self.feed.iqoption.submit_order(
                    symbol=symbol,
                    side=cfd_side,
                    amount=actual_investment,
                    leverage=500,
                    stop_loss_pct=sl_pct,
                    take_profit_pct=tp_pct
                )
            finally:
                self._iqoption_order_pending = False
            if iq_res.get("success"):
                oid = iq_res.get("order_id", "")
                position["broker_order_id"] = oid
                actual_sym = iq_res.get("symbol", symbol)
                position["symbol"] = actual_sym
                position["name"] = self.feed.assets.get(actual_sym, {}).get("name", position["name"])
                symbol = actual_sym
                mode_str = "REAL" if is_broker_live else "DEMO/PRACTICE"
                dir_label = "🔻 CORTO (SELL)" if cfd_side == "sell" else "🟢 LARGO (BUY)"
                wallet["cash"] = round(wallet["cash"] - actual_investment, 2)
                self.cash_balance = wallet["cash"]
                self.agent._add_thought(f"📈 ORDEN FOREX CFD IQ OPTION ({mode_str}): {dir_label} en {symbol} (ID: {oid}) x500. SL: {sl_pct}% | TP: {tp_pct}%.", "INFO", symbol, "⚡")
            else:
                err_msg = str(iq_res.get('error', 'Error desconocido'))
                is_closed_or_suspended = any(k in err_msg.lower() for k in ["not available", "suspended", "not found", "closed"])
                cooldown_dur = 600.0 if is_closed_or_suspended else 120.0
                self.last_exit_times[symbol] = time.time() + cooldown_dur
                self._broker_order_failure_cooldown["IQOPTION"] = time.time() + 30.0
                self.agent.learner.penalize(symbol, penalty=30.0)

                if is_closed_or_suspended:
                    self.agent._add_thought(f"⏸️ Horario IQ Option: {symbol} cerrado en este momento. Pausado preventivamente 10m para operar activos abiertos.", "INFO", symbol, "⏸️")
                else:
                    self.agent._add_thought(f"🛑 Error en broker IQ Option: {err_msg}. Operación abortada.", "WARNING", symbol, "🛑")
                return

        self.open_positions[symbol] = position
        if hasattr(self, "risk_manager"):
            self.risk_manager.register_trade_open()

        b_curr = "COP" if (hasattr(self.feed, 'iqoption') and getattr(self.feed.iqoption, "currency", "USD") == "COP") else "USD"
        self.agent._add_thought(
            f"🛒 ¡COMPRADO [📈 IQ Option]! {quantity} {symbol} ({asset['name']}) por {b_curr} {actual_investment:,.2f}. Kelly: {kelly_pct}% | Meta: ${take_profit:,.2f} | Escudo: ${stop_loss:,.2f}.",
            "TRADE_BUY",
            symbol,
            icon="⚡"
        )

    def _execute_sell(self, symbol: str, asset: Dict[str, Any], decision_data: Dict[str, Any]):
        if symbol not in self.open_positions:
            return
        
        pos = self.open_positions.pop(symbol)
        actual_sym = pos.get("symbol", symbol)
        exit_price = asset["price"]
        quantity = pos["quantity"]
        invested = pos["invested_amount"]
        entry_p = pos.get("entry_price", exit_price)
        broker_id = pos.get("broker", self.active_broker)

        # En dinero real, nunca se acredita PnL local ni se libera el cupo
        # hasta que la siguiente reconciliación confirme el cierre en IQ Option.
        wallet = self.broker_wallets.get(broker_id, self.broker_wallets.get("IQOPTION", {}))
        is_broker_live = wallet.get("environment") == "LIVE_REAL"
        if broker_id == "IQOPTION" and is_broker_live:
            pos_id = pos.get("broker_order_id") or pos.get("position_id") or pos.get("id")
            if not pos_id:
                self.open_positions[symbol] = pos
                self.agent._add_thought(
                    f"⚠️ Cierre de {symbol} bloqueado: falta identificador de posición IQ Option. Reconciliación requerida.",
                    "WARNING",
                    symbol,
                    "⚠️",
                )
                return

            close_res = self.feed.iqoption.close_position(str(pos_id))
            if not close_res.get("success"):
                self.open_positions[symbol] = pos
                self.agent._add_thought(
                    f"⚠️ Cierre IQ Option no confirmado para {symbol}: {close_res.get('error', 'sin confirmación')}. Posición retenida.",
                    "WARNING",
                    symbol,
                    "⚠️",
                )
                return

            pos["execution_state"] = "PENDING_CLOSE_RECONCILIATION"
            pos["close_requested_at"] = time.time()
            pos["close_reason"] = decision_data.get("reason_simple", "Cierre solicitado")
            self.open_positions[symbol] = pos
            self.agent._add_thought(
                f"📤 Cierre enviado a IQ Option para {symbol}. PnL y cupo quedan pendientes de reconciliación del broker.",
                "INFO",
                symbol,
                "📤",
            )
            return

        if broker_id == "IQOPTION":
            pos_side = pos.get("side", "BUY_LONG").upper()
            # MODO FOREX CFD CON STOP-LOSS Y TAKE-PROFIT AUTOMÁTICOS:
            if pos_side in ["BUY", "BUY_LONG", "CALL"]:
                diff_pct = ((exit_price - entry_p) / entry_p) if entry_p > 0 else 0.0
            else:
                diff_pct = ((entry_p - exit_price) / entry_p) if entry_p > 0 else 0.0

            # Multiplicador CFD controlado con apalancamiento estándar (x10)
            cfd_return = max(-1.0, min(2.5, diff_pct * 10.0))
            pnl = round(invested * cfd_return, 2)
            exit_value = round(max(0.0, invested + pnl), 2)
            pnl_pct = round(cfd_return * 100, 2)
        else:
            exit_value = round(quantity * exit_price, 2)
            pnl = round(exit_value - invested, 2)
            pnl_pct = round(((exit_price - entry_p) / entry_p) * 100, 2) if entry_p > 0 else 0.0

        wallet = self.broker_wallets.get(broker_id, self.broker_wallets.get("IQOPTION", {}))
        b_icon = wallet.get("icon", "📈")
        broker_badge = f"{b_icon} {wallet.get('name', broker_id)}"

        # SIN BÓVEDA: El retorno total (inversión + pnl) se reintegra al 100% de forma transparente en el monedero
        wallet["cash"] = round(wallet["cash"] + exit_value, 2)
        if broker_id == self.active_broker:
            self.cash_balance = wallet["cash"]

        # Enrutamiento de venta / cierre en IQ Option (Forex CFD cierre de posición)
        if hasattr(self.feed, "iqoption"):
            pos_id = pos.get("broker_order_id")
            if pos_id:
                iq_res = self.feed.iqoption.close_position(pos_id)
                if not iq_res.get("success"):
                    self.agent._add_thought(f"ℹ️ Cierre registrado en IQ Option: {iq_res.get('error', 'Completado')}", "INFO", symbol, "📈")

        trade_record = {
            "symbol": symbol,
            "name": pos["name"],
            "broker": broker_id,
            "environment": wallet.get("environment", "PAPER"),
            "category": pos.get("category", "TRADFI_STOCK"),
            "side": "BUY_LONG",
            "quantity": quantity,
            "entry_price": pos["entry_price"],
            "exit_price": exit_price,
            "invested_amount": invested,
            "exit_value": exit_value,
            "pnl": pnl,
            "pnl_percent": pnl_pct,
            "entry_time": pos.get("entry_time", datetime.datetime.now().strftime("%H:%M:%S")),
            "exit_time": datetime.datetime.now().strftime("%H:%M:%S"),
            "reason": decision_data.get("reason_simple", "Venta ejecutada"),
            "exit_reason": decision_data.get("reason_simple", "Venta ejecutada"),
            "exit_type": decision_data.get("decision", "SELL"),
            "success": pnl > 0
        }
        self.journal.record_trade(trade_record)
        self.agent.record_trade_result(trade_record)
        self.last_exit_times[symbol] = time.time()
        if hasattr(self, "risk_manager"):
            self.risk_manager.register_trade_close(pnl, symbol=symbol, is_intraday=True, broker_id=broker_id)
        if broker_id == "IQOPTION":
            self.iqoption_risk_policy.record_closed_trade(pnl)
            self._apply_iqoption_daily_halt()

        b_curr = "COP" if (broker_id == "IQOPTION" and getattr(self.feed.iqoption, "currency", "USD") == "COP") else "USD"
        trade_label = "Forex CFD (SL/TP)" if broker_id == "IQOPTION" else "Spot"
        if pnl > 0:
            self.agent._add_thought(
                f"💰 ¡OPERACIÓN GANADA [{broker_badge} - {trade_label}]! {symbol} cerrado a ${exit_price:,.2f}. Retorno: +{b_curr} {pnl:,.2f} (+{pnl_pct:.2f}%). Saldo acreditado directamente a tu cuenta.",
                "TRADE_WIN",
                symbol,
                icon="💵"
            )
        elif pnl == 0:
            self.agent._add_thought(
                f"⚖️ EMPATE [{broker_badge} - {trade_label}]: {symbol} cerrado al precio de entrada (${exit_price:,.2f}). Inversión de {b_curr} {invested:,.2f} reembolsada al 100%.",
                "INFO",
                symbol,
                icon="⚖️"
            )
        else:
            self.agent._add_thought(
                f"🛡️ CIERRE DEFENSIVO STOP-LOSS [{broker_badge} - {trade_label}]: {symbol} cerrado a ${exit_price:,.2f}. Pérdida controlada: -{b_curr} {abs(pnl):,.2f} ({pnl_pct:.2f}%).",
                "TRADE_LOSS",
                symbol,
                icon="🛑"
            )

    def emergency_close_all(self, broker: Optional[str] = None):
        target_b = broker.upper() if broker else None

        if target_b and target_b in self.broker_wallets:
            # Pausar y cerrar EXCLUSIVAMENTE el broker indicado (aislamiento estricto)
            b_wal = self.broker_wallets[target_b]
            b_wal["is_running"] = False
            b_name = b_wal.get("name", target_b)
            self.agent._add_thought(
                f"🛑 PARADA DE EMERGENCIA [{b_name}]: Operaciones de este broker DETENIDAS por completo. Los demás brokers continúan operando normalmente.",
                "WARNING",
                icon="🛑"
            )
            for pos_key in list(self.open_positions.keys()):
                pos = self.open_positions.get(pos_key)
                if not pos: continue
                pos_b = (pos.get("broker") or "IQOPTION").upper()
                if pos_b == target_b:
                    actual_sym = pos.get("symbol", pos_key)
                    asset = self.feed.get_asset(actual_sym) or {"price": pos.get("current_price", pos.get("entry_price", 1.0)), "name": pos.get("name", actual_sym)}
                    decision = {
                        "decision": "EMERGENCY_SELL",
                        "reason_simple": f"Parada de Seguridad solicitada exclusivamente para {b_name}"
                    }
                    self._execute_sell(pos_key, asset, decision)
        else:
            # Si no se especificó broker, detener todos
            self.is_running = False
            for b_id, b_wal in self.broker_wallets.items():
                b_wal["is_running"] = False
            self.agent._add_thought("🛑 PARADA DE EMERGENCIA GLOBAL: Operaciones detenidas en todos los brokers.", "WARNING", icon="🛑")
            for pos_key in list(self.open_positions.keys()):
                pos = self.open_positions.get(pos_key)
                if not pos: continue
                actual_sym = pos.get("symbol", pos_key)
                asset = self.feed.get_asset(actual_sym) or {"price": pos.get("current_price", pos.get("entry_price", 1.0)), "name": pos.get("name", actual_sym)}
                decision = {
                    "decision": "EMERGENCY_SELL",
                    "reason_simple": "Cierre Inmediato de Seguridad / Parada solicitada por el usuario"
                }
                self._execute_sell(pos_key, asset, decision)

        # El motor general sigue activo si al menos un broker continúa operando
        self.is_running = any(w.get("is_running", True) for w in self.broker_wallets.values())

    def toggle_pause(self, broker: Optional[str] = None) -> bool:
        target_b = (broker or self.active_broker).upper()
        b_wal = self.broker_wallets.get(target_b, self.broker_wallets.get("IQOPTION", {}))
        b_name = b_wal.get("name", target_b)

        currently_running = b_wal.get("is_running", True)
        new_running_state = not currently_running
        b_wal["is_running"] = new_running_state

        if new_running_state:
            b_wal["target_reached"] = False
            b_wal["loss_limit_reached"] = False
            self.target_reached = False
            self.loss_limit_reached = False
            if getattr(self, "iq_mode", "FOREX_CFD") == "BINARY_OPTIONS":
                self.iqoption_risk_policy.zero_loss_blocks_entries = False
            self.agent._add_thought(
                f"▶️ [{b_name}] Operaciones REANUDADAS para este broker. Escáner y ejecuciones activas.",
                "INFO",
                icon="▶️"
            )
        else:
            self.agent._add_thought(
                f"⏸️ [{b_name}] Operaciones PAUSADAS. No se realizarán nuevas compras ni ventas en {b_name}.",
                "INFO",
                icon="⏸️"
            )

        self.is_running = new_running_state
        return new_running_state

    def get_state(self) -> Dict[str, Any]:
        active_b = "IQOPTION"
        wallet = self.broker_wallets.get("IQOPTION", {})
        
        # Posiciones activas de IQ Option: Reúne todas las posiciones reales de margen (Forex CFD) y Opciones Binarias activas (Cero borrado)
        active_positions = list(self.get_broker_positions(active_b))
        if hasattr(self, "binary_engine") and self.binary_engine.open_position:
            b_pos = self.binary_engine.open_position
            rem_s = max(0, int(b_pos["expiration_timestamp"] - time.time()))
            cur_price = self.feed.assets.get(b_pos["symbol"], {}).get("price", b_pos["entry_price"])
            active_positions.append({
                "symbol": b_pos["symbol"],
                "name": f"{b_pos['symbol']} [Turbo {b_pos['direction']}]",
                "broker": "IQOPTION",
                "category": "OPTIONS",
                "side": b_pos["direction"],
                "invested_amount": b_pos["amount"],
                "entry_price": b_pos["entry_price"],
                "current_price": cur_price,
                "current_pnl": 0.0,
                "current_pnl_percent": 0.0,
                "icon": "⏱️",
                "direction": b_pos["direction"],
                "payout": b_pos["payout"],
                "potential_profit": b_pos["potential_profit"],
                "status_label": f"Expira en {rem_s}s"
            })
        invested = sum(pos["invested_amount"] for pos in active_positions)
        unrealized_pnl = sum(pos.get("current_pnl", 0.0) for pos in active_positions)
        if active_b == "IQOPTION":
            # Sincronización real institucional con IQ Option:
            # "Disponible" = Saldo de efectivo menos margen comprometido en posiciones abiertas y pérdidas flotantes
            cash_avail = max(0.0, round(wallet.get("cash", 0.0) - invested + min(0.0, unrealized_pnl), 2))
            total_equity = round(wallet.get("cash", 0.0) + unrealized_pnl, 2)
        else:
            cash_avail = wallet["cash"]
            total_equity = self.get_broker_equity(active_b)
        initial_bal = wallet["initial_balance"]
        active_env = wallet.get("environment", self.execution_environment)
        realized_stats = self.journal.get_statistics(broker=active_b, environment=active_env)
        completed_trades = self.journal.get_trades(35, broker=active_b, environment=active_env)
        
        if active_b == "IQOPTION":
            # Para IQ Option (Cero bóveda artificial): El rendimiento real acumulado es la diferencia neta entre la equity actual y el capital base
            if initial_bal > 0:
                total_profit = round(total_equity - initial_bal, 2)
                total_profit_pct = round((total_profit / initial_bal) * 100, 2)
            else:
                total_profit = round(unrealized_pnl, 2)
                total_profit_pct = 0.0
        else:
            vault_val = round(self.get_broker_vault(active_b, active_env), 2)
            total_profit = round(vault_val + unrealized_pnl, 2)
            total_profit_pct = round((total_profit / initial_bal) * 100, 2) if initial_bal > 0 else 0.0

        risk_snapshot = self.iqoption_risk_policy.snapshot()
        self._apply_iqoption_daily_halt()
        broker_running = wallet.get("is_running", True)
        is_binary = (getattr(self, "iq_mode", "FOREX_CFD") == "BINARY_OPTIONS")

        if risk_snapshot.get("halted_reason") == "META_DIARIA_ALCANZADA":
            status_text = "🏆 META DE GANANCIA LOGRADA (DETENIDO)"
        elif risk_snapshot.get("halted_reason") == "LIMITE_PERDIDA_DIARIA_ALCANZADO":
            status_text = "🛑 LÍMITE PÉRDIDA ALCANZADO (DETENIDO)"
        elif not broker_running:
            status_text = "EN PAUSA"
        elif is_binary:
            status_text = "OPERANDO EN VIVO (BINARIAS 1 A LA VEZ)"
        elif risk_snapshot.get("halted_reason") == "TOLERANCIA_CERO_BLOQUEA_NUEVAS_ENTRADAS":
            status_text = "🛡️ TOLERANCIA CERO: ENTRADAS BLOQUEADAS"
        else:
            status_text = "OPERANDO EN VIVO (24/7)"

        # Filtrado estricto por broker: SOLO activos permitidos para este broker (Cero mezcla)
        market_radar = []
        target_cat = wallet.get("allowed_categories", ["FOREX", "CFD", "OPTIONS"])
        broker_assets = [a for a in self.feed.get_all_assets() if a.get("category") in target_cat]

        for asset in broker_assets:
            eval_result = self.agent.evaluate_asset(asset, self.open_positions)
            exp = self.agent.learner.asset_stats.get(asset["symbol"], {})
            is_cooling = self.agent.learner.is_asset_in_cooldown(asset["symbol"])
            
            market_radar.append({
                "symbol": asset["symbol"],
                "name": asset["name"],
                "category": asset.get("category", "TRADFI_STOCK"),
                "type": asset["type"],
                "icon": asset.get("icon", "📈"),
                "price": asset["price"],
                "change_percent": asset["change_percent"],
                "trend_status": asset["trend_status"],
                "rsi": asset["rsi"],
                "support": asset["support"],
                "resistance": asset["resistance"],
                "source": asset.get("source", "SIMULATION"),
                "ai_decision": eval_result["decision"],
                "ai_confidence": eval_result["confidence"],
                "ai_reason": eval_result["reason_simple"],
                "is_open": asset["symbol"] in self.open_positions,
                "is_cooling": is_cooling,
                "cooldown_remaining": exp.get("cooldown_remaining_sec", 0),
                "safe_kelly_pct": exp.get("safe_kelly_pct", 20.0),
                "profit_factor": exp.get("profit_factor", 1.0),
                "expectancy": exp.get("expectancy", 0.0),
                "expert_tag": exp.get("expert_tag", "⚖️ En Análisis Cuantitativo"),
                "regime": eval_result.get("regime", "RANGING_SIDEWAYS"),
                "regime_tag": eval_result.get("regime_tag", "⚖️ Consolidación")
            })

        if hasattr(self.feed, 'iqoption') and self.feed.iqoption.is_configured:
            is_iq_conn = getattr(self.feed.iqoption, 'connected', True)
            iq_mode = "MODO REAL (EN VIVO)" if self.feed.iqoption.environment == "LIVE_REAL" else "MODO PRÁCTICA (DEMO)"
            iqoption_status = {
                "connected": is_iq_conn,
                "status": f"CONECTADO A IQ OPTION ({iq_mode})" if is_iq_conn else "DESCONECTADO",
                "environment": self.feed.iqoption.environment,
                "balance": self.feed.iqoption.balance,
                "currency": getattr(self.feed.iqoption, "currency", "COP")
            }
        else:
            iqoption_status = {
                "connected": True,
                "status": "MODO SIMULACIÓN (PAPER)",
                "mode": "PAPER_SIMULATION"
            }
        learning_summary = self.agent.learner.get_learning_summary()

        brokers_dict = {}
        for b_id, b_wal in self.broker_wallets.items():
            is_conn = iqoption_status.get("connected", True)
            status_lbl = iqoption_status.get("status", "MODO SIMULACIÓN (PAPER)")
            cat_tag = "Forex / CFDs"
            iq_user = (self.feed.iqoption.profile_data.get("name") or self.feed.iqoption.email) if hasattr(self.feed, 'iqoption') and self.feed.iqoption.is_configured else ""
            iq_real = round(self.feed.iqoption.real_amount, 2) if hasattr(self.feed, 'iqoption') else 0.0
            iq_demo = round(self.feed.iqoption.practice_amount, 2) if hasattr(self.feed, 'iqoption') else 10000.0

            brokers_dict[b_id] = {
                "id": b_id,
                "name": b_wal.get("name", b_id),
                "icon": b_wal.get("icon", "💼"),
                "category_tag": cat_tag,
                "connected": is_conn,
                "environment": b_wal.get("environment", "PAPER"),
                "status_text": status_lbl,
                "equity": self.get_broker_equity(b_id),
                "cash": self.get_broker_cash(b_id),
                "profit_vault": 0.0,
                "initial_balance": round(b_wal.get("initial_balance", 0.0), 2),
                "positions_count": len(self.get_broker_positions(b_id)),
                "logged_user": iq_user if b_id == "IQOPTION" else "",
                "user_email": self.feed.iqoption.email if (b_id == "IQOPTION" and hasattr(self.feed, 'iqoption')) else "",
                "real_balance": iq_real if b_id == "IQOPTION" else None,
                "practice_balance": iq_demo if b_id == "IQOPTION" else None,
                "is_running": b_wal.get("is_running", True),
                "currency": getattr(self.feed.iqoption, "currency", "COP") if (b_id == "IQOPTION" and hasattr(self.feed, 'iqoption')) else "USD"
            }

        # Enfoque exclusivo en IQ Option para el dashboard y la API (elimina Alpaca y Binance de la interfaz)
        if "IQOPTION" in brokers_dict:
            brokers_dict = {"IQOPTION": brokers_dict["IQOPTION"]}

        return {
            "system_status": {
                "is_running": broker_running,
                "global_is_running": self.is_running,
                "status_text": status_text,
                "active_broker": "IQOPTION",
                "operating_mode": self.operating_mode,
                "iq_mode": getattr(self, "iq_mode", "FOREX_CFD"),
                "execution_environment": self.execution_environment,
                "paper_initial_balance": initial_bal,
                "active_assets_count": len(market_radar),
                "profit_target_enabled": self.profit_target_enabled,
                "profit_target_amount": wallet.get("target_amount", self.profit_target_amount),
                "target_reached": self.target_reached,
                "max_loss_enabled": self.max_loss_enabled,
                "max_loss_amount": wallet.get("max_loss_amount", self.max_loss_amount),
                "loss_limit_reached": self.loss_limit_reached,
                "risk_policy": risk_snapshot,
                "brokers": brokers_dict,
                "broker_connections": {
                    "iqoption": iqoption_status
                }
            },
            "financial_summary": {
                "total_equity": total_equity,
                "cash_available": cash_avail,
                "currency": getattr(self.feed.iqoption, "currency", "COP") if (active_b == "IQOPTION" and hasattr(self.feed, 'iqoption')) else "USD",
                "invested_capital": round(invested, 2),
                "initial_balance": initial_bal,
                "operating_capital_base": cash_avail,
                "profit_vault": 0.0,
                "total_profit_usd": total_profit,
                "total_profit_percent": total_profit_pct,
                "unrealized_pnl": round(unrealized_pnl, 2),
                "realized_pnl": realized_stats["total_realized_pnl"],
                "win_rate": realized_stats["win_rate"],
                "total_trades_count": realized_stats["total_trades"],
                "winning_trades_count": realized_stats["winning_trades"],
                "losing_trades_count": realized_stats["losing_trades"],
                "tie_trades_count": realized_stats.get("tie_trades", 0),
                "profit_factor": learning_summary.get("portfolio_profit_factor", realized_stats["profit_factor"]),
                "portfolio_expectancy": learning_summary.get("portfolio_expectancy", 0.0),
                "mastery_level": learning_summary.get("mastery_level", "🌱 Cadete Algorítmico")
            },
            "funding_arbitrage": {
                "top_opportunity": self.agent.funding_scanner.get_top_opportunity(),
                "all_rates": self.agent.funding_scanner.scan_all_crypto()
            },
            "news_macro_shield": self.agent.sentiment_shield.get_shield_summary(),
            "learning_summary": learning_summary,
            "active_positions": active_positions,
            "completed_trades": completed_trades,
            "market_radar": market_radar,
            "agent_thoughts": self.agent.get_thoughts(30),
            "equity_history": self.equity_history,
            "binary_options": self.binary_engine.get_status() if hasattr(self, "binary_engine") else {}
        }

    def get_full_state(self) -> Dict[str, Any]:
        return self.get_state()

    def close_position(self, symbol: str, reason: str = "Cierre manual por usuario") -> Optional[Dict[str, Any]]:
        if symbol not in self.open_positions:
            return None
        asset = self.feed.get_asset(symbol)
        if not asset:
            return None
        decision = {
            "decision": "MANUAL_SELL",
            "reason_simple": reason
        }
        self._execute_sell(symbol, asset, decision)
        return {"symbol": symbol, "status": "CLOSED"}

    def transfer_vault_to_capital(self, broker: Optional[str] = None, amount: Optional[float] = None) -> Dict[str, Any]:
        b = "IQOPTION"
        wallet = self.broker_wallets.get("IQOPTION")
        if not wallet:
            return {"success": False, "error": "Wallet IQ Option no encontrada"}
        
        current_vault = wallet.get("profit_vault", 0.0)
        if current_vault <= 0:
            return {"success": False, "error": "No hay ganancias acumuladas en la bóveda para transferir"}
        
        transfer_amount = current_vault if (amount is None or amount <= 0) else min(current_vault, round(float(amount), 2))
        
        wallet["profit_vault"] = round(wallet["profit_vault"] - transfer_amount, 2)
        wallet["initial_balance"] = round(wallet["initial_balance"] + transfer_amount, 2)
        wallet["cash"] = round(wallet["cash"] + transfer_amount, 2)
        
        self.save_broker_vault("IQOPTION", wallet["profit_vault"], wallet.get("environment"))
        self.broker_config["iqoption_initial_balance"] = wallet["initial_balance"]
        save_broker_config(self.broker_config)
        
        self.initial_balance = wallet["initial_balance"]
        self.cash_balance = wallet["cash"]
            
        self.agent._add_thought(
            f"💼 BÓVEDA TRANSFERIDA A CAPITAL [IQ Option]: Se transfirieron ${transfer_amount:,.2f} USD de ganancias acumuladas al Capital Operativo. "
            f"Nueva base operativa: ${wallet['initial_balance']:,.2f} USD. Bóveda restante: ${wallet['profit_vault']:,.2f} USD.",
            "INFO",
            icon="💼"
        )
        return {
            "success": True,
            "broker": "IQOPTION",
            "transferred_amount": transfer_amount,
            "new_initial_balance": wallet["initial_balance"],
            "new_cash": wallet["cash"],
            "remaining_vault": wallet["profit_vault"]
        }

    def harvest_vault_profits(self, broker: Optional[str] = None) -> Dict[str, Any]:
        """
        Cierra todas las posiciones abiertas que tengan ganancia positiva (> 0)
        para consolidar y trasladar de inmediato sus ganancias a la Bóveda protegida.
        """
        closed = []
        total_harvested = 0.0

        for sym in list(self.open_positions.keys()):
            pos = self.open_positions[sym]
            pnl_amount = pos.get("current_pnl", 0.0)
            if pnl_amount > 0:
                asset = self.feed.get_asset(sym)
                if asset:
                    decision = {
                        "decision": "HARVEST_VAULT",
                        "reason_simple": f"🔒 Cosecha a Bóveda: Beneficio asegurado de +${pnl_amount:,.2f} USD (+{pos.get('current_pnl_percent', 0.0):.2f}%)"
                    }
                    self._execute_sell(sym, asset, decision)
                    closed.append({"symbol": sym, "pnl": pnl_amount})
                    total_harvested += pnl_amount

        wallet = self.broker_wallets.get("IQOPTION", {})
        return {
            "success": True,
            "broker": "IQOPTION",
            "closed_count": len(closed),
            "total_harvested_usd": round(total_harvested, 2),
            "new_vault_balance": wallet.get("profit_vault", 0.0),
            "new_cash_balance": wallet.get("cash", 0.0),
            "closed_trades": closed
        }

    def reset_account(self):
        self.emergency_close_all()
        self.cash_balance = self.initial_balance
        self.target_reached = False
        self.loss_limit_reached = False
        self.is_running = True
        self.equity_history = []
        self._record_equity_snapshot()
        self.agent._add_thought("🔄 Cuenta reiniciada con saldo inicial de $10,000.00 USD.", "INFO", icon="🔄")

    def get_asset_candles(self, symbol: str, timeframe: str = "1m", limit: int = 100) -> Dict[str, Any]:
        sym = symbol.upper()
        asset = self.feed.get_asset(sym)
        if not asset:
            return {"error": f"Activo {symbol} no encontrado en el catálogo", "candles": []}

        candles = self.feed.get_candles(sym, timeframe=timeframe, limit=limit)
        pos = self.open_positions.get(sym)

        eval_res = self.agent.evaluate_asset(asset, self.open_positions)

        return {
            "symbol": sym,
            "name": asset.get("name", sym),
            "category": asset.get("category", "FOREX"),
            "icon": asset.get("icon", "📈"),
            "price": asset.get("price", 0.0),
            "open_price": asset.get("open_price", 0.0),
            "change_percent": asset.get("change_percent", 0.0),
            "high_24h": asset.get("high_24h", 0.0),
            "low_24h": asset.get("low_24h", 0.0),
            "volume": asset.get("volume", 0),
            "rsi": asset.get("rsi", 50.0),
            "support": asset.get("support", 0.0),
            "resistance": asset.get("resistance", 0.0),
            "trend_status": asset.get("trend_status", ""),
            "ai_decision": eval_res.get("decision", "HOLD"),
            "ai_confidence": eval_res.get("confidence", 50),
            "timeframe": timeframe,
            "candles": candles,
            "position": {
                "is_open": True,
                "entry_price": pos.get("entry_price"),
                "current_price": pos.get("current_price"),
                "stop_loss": pos.get("stop_loss"),
                "take_profit": pos.get("take_profit"),
                "quantity": pos.get("quantity"),
                "current_pnl": pos.get("current_pnl"),
                "current_pnl_percent": pos.get("current_pnl_percent")
            } if pos else {"is_open": False}
        }

    def add_broker(self, broker_id: str, api_key: str = "", secret_key: str = "", initial_balance: float = 1000.0) -> Dict[str, Any]:
        """Deshabilitado: la plataforma usa exclusivamente IQ Option."""
        return {
            "success": False,
            "error": "PLATAFORMA_EXCLUSIVA_IQOPTION: no se permite agregar brokers."
        }
