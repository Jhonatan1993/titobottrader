import time
import datetime
from typing import Dict, List, Any, Optional
from market_data.market_feed import MultiAssetMarketFeed
from ai_analysis.intelligent_agent import IntelligentTradingAgent
from trade_journal.journal import TradeJournal
from config.broker_config import load_broker_config, save_broker_config
from execution.alpaca_adapter import AlpacaAdapter
from execution.binance_adapter import BinanceAdapter
from risk_management.risk_manager import RiskManager

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
        self.operating_mode = self.broker_config.get("operating_mode", "UNIFIED_TRADFI_CRYPTO")
        self.execution_environment = execution_environment or self.broker_config.get("execution_environment", "PAPER")
        
        saved_paper = float(self.broker_config.get("paper_initial_balance", 10000.0))
        self.paper_initial_balance = initial_balance if initial_balance is not None else saved_paper

        if self.execution_environment == "PAPER":
            self.initial_balance = self.paper_initial_balance
            self.cash_balance = self.paper_initial_balance
        else:
            self.initial_balance = initial_balance if initial_balance is not None else 10000.0
            self.cash_balance = self.initial_balance
        self.max_open_positions = max_open_positions
        self.is_running = True

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
        self.profit_target_enabled = bool(self.broker_config.get("profit_target_enabled", True))
        self.profit_target_amount = float(self.broker_config.get("profit_target_amount", 500.0))
        self.target_reached = False

        self.max_loss_enabled = bool(self.broker_config.get("max_loss_enabled", True))
        self.max_loss_amount = float(self.broker_config.get("max_loss_amount", 150.0))
        self.loss_limit_reached = False

        self.feed = MultiAssetMarketFeed()
        self.agent = IntelligentTradingAgent()
        self.journal = TradeJournal()
        self.active_broker = self.broker_config.get("active_broker", "BINANCE").upper()
        alpaca_paper_init = float(self.broker_config.get("alpaca_initial_balance", 252.65))
        binance_paper_init = float(self.broker_config.get("paper_initial_balance", 30.0))
        binance_vault = float(self.broker_config.get("binance_profit_vault", 0.0))
        alpaca_vault = float(self.broker_config.get("alpaca_profit_vault", 0.0))

        # Billeteras y Parámetros Aislados por Broker (Arquitectura Modular Simétrica)
        binance_env = self.broker_config.get("binance_environment", self.broker_config.get("execution_environment", "PAPER"))
        alpaca_env = self.broker_config.get("alpaca_environment", "PAPER")

        self.broker_wallets: Dict[str, Dict[str, Any]] = {
            "BINANCE": {
                "id": "BINANCE",
                "name": "Binance Spot",
                "icon": "🪙",
                "category": "CRYPTO",
                "allowed_categories": ["CRYPTO"],
                "environment": binance_env,
                "initial_balance": binance_paper_init,
                "cash": binance_paper_init,
                "profit_vault": binance_vault,
                "target_amount": float(self.broker_config.get("profit_target_amount", 3000.0)),
                "max_loss_amount": float(self.broker_config.get("max_loss_amount", 0.0)),
                "target_reached": False,
                "loss_limit_reached": False,
                "is_running": True
            },
            "ALPACA": {
                "id": "ALPACA",
                "name": "Alpaca Wall Street",
                "icon": "🏛️",
                "category": "TRADFI",
                "allowed_categories": ["TRADFI_STOCK", "ETF"],
                "environment": alpaca_env,
                "initial_balance": alpaca_paper_init,
                "cash": alpaca_paper_init,
                "profit_vault": alpaca_vault,
                "target_amount": float(self.broker_config.get("alpaca_profit_target_amount", 5000.0)),
                "max_loss_amount": float(self.broker_config.get("alpaca_max_loss_amount", 10.0)),
                "target_reached": False,
                "loss_limit_reached": False,
                "is_running": True
            }
        }

        # Carga dinámica de brokers adicionales conectados por el usuario
        custom_b = self.broker_config.get("custom_brokers", {})
        for cb_id, cb_data in custom_b.items():
            self.broker_wallets[cb_id] = cb_data

        self.open_positions: Dict[str, Dict[str, Any]] = {}
        self.equity_history: List[Dict[str, Any]] = []
        self.last_exit_times: Dict[str, float] = {}

        # Sincronización con Alpaca según entorno (Paper vs Real)
        if alpaca_env == "LIVE_REAL":
            self.feed.alpaca.base_url = "https://api.alpaca.markets"
            if self.feed.alpaca.is_configured:
                alp_acc = self.feed.alpaca.get_account_summary()
                if alp_acc.get("connected"):
                    self.broker_wallets["ALPACA"]["cash"] = float(alp_acc.get("cash", alpaca_paper_init))
                    alp_vault = float(self.broker_wallets["ALPACA"].get("profit_vault", 0.0))
                    total_eq = float(alp_acc.get("equity", alpaca_paper_init))
                    self.broker_wallets["ALPACA"]["initial_balance"] = max(0.0, round(total_eq - alp_vault, 2))
        else:
            self.feed.alpaca.base_url = "https://paper-api.alpaca.markets"

        # Si se especificó un saldo inicial explícito al instanciar (ej. en tests), respetarlo en el broker activo
        if initial_balance is not None:
            active_b = self.active_broker
            if active_b in self.broker_wallets:
                self.broker_wallets[active_b]["initial_balance"] = float(initial_balance)
                self.broker_wallets[active_b]["cash"] = float(initial_balance)
                self.broker_wallets[active_b]["profit_vault"] = 0.0

        # Asignar saldo activo según el broker en vista
        active_wallet = self.broker_wallets.get(self.active_broker, self.broker_wallets["BINANCE"])
        self.cash_balance = active_wallet["cash"]
        self.initial_balance = active_wallet["initial_balance"]
        self.execution_environment = active_wallet.get("environment", "PAPER")

        # Si el entorno guardado en Binance es LIVE_REAL, verificar obligatoriamente la autenticación real
        if binance_env == "LIVE_REAL":
            is_authenticated = False
            if self.feed.binance.is_configured:
                self.feed.binance.live_trading_enabled = True
                acc = self.feed.binance.get_account_balances()
                if acc.get("authenticated"):
                    is_authenticated = True
                    self._sync_binance_wallet_positions(acc)
                    saved_real_init = float(self.broker_config.get("real_initial_balance", 0.0))
                    self.broker_wallets["BINANCE"]["initial_balance"] = saved_real_init if saved_real_init > 0 else round(self.broker_wallets["BINANCE"]["cash"] + self.get_invested_capital(), 2)
                    self.broker_wallets["BINANCE"]["environment"] = "LIVE_REAL"
                    if self.active_broker == "BINANCE":
                        self.initial_balance = self.broker_wallets["BINANCE"]["initial_balance"]
                        self.loss_limit_reached = False
                else:
                    err_msg = acc.get("error", "Error de autenticación API")
                    self.agent._add_thought(
                        f"🛡️ BLOQUEO DE SEGURIDAD: Falló autenticación con Binance ({err_msg}). Forzando MODO SIMULACIÓN (PAPER).",
                        "WARNING",
                        icon="🛑"
                    )

            if not is_authenticated:
                self.broker_wallets["BINANCE"]["environment"] = "PAPER"
                self.feed.binance.live_trading_enabled = False
                self.broker_config["binance_environment"] = "PAPER"
                self.broker_config["execution_environment"] = "PAPER"
                if self.active_broker == "BINANCE":
                    self.execution_environment = "PAPER"
                    self.paper_initial_balance = float(self.broker_config.get("paper_initial_balance", 10000.0))
                    self.cash_balance = self.paper_initial_balance
                    self.initial_balance = self.paper_initial_balance
                save_broker_config(self.broker_config)

        self.agent.update_learning_from_disk()
        self._record_equity_snapshot()

    def _sync_binance_wallet_positions(self, acc: Dict[str, Any]):
        """
        Sincroniza activos existentes en la billetera real Spot de Binance (ej: BTC, ETH, etc.)
        para que aparezcan inmediatamente en las posiciones abiertas y el motor los gestione.
        Filtra automáticamente saldos residuales o 'polvo' (< $5.00 USD) que no cumplen con
        el tamaño mínimo nocional de orden en Binance.
        """
        if not acc.get("authenticated"):
            return
        usdt_val = float(acc.get("usdt_free", 0.0))
        total_stable = float(acc.get("total_stable_free", 0.0))
        real_cash = usdt_val if usdt_val > 0 else total_stable
        
        # Sincronizar efectivo real directamente a la cartera de Binance
        self.broker_wallets["BINANCE"]["cash"] = round(real_cash, 2)
        if self.active_broker == "BINANCE":
            self.cash_balance = round(real_cash, 2)

        balances = acc.get("balances", {})
        active_synced_symbols = set()
        total_crypto_invested = 0.0

        for c_sym in ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK", "NEAR"]:
            asset_data = balances.get(c_sym)
            if asset_data:
                qty = float(asset_data.get("free", 0.0)) + float(asset_data.get("locked", 0.0))
                cur_asset = self.feed.get_asset(c_sym)
                if cur_asset and qty > 0:
                    cur_p = cur_asset["price"]
                    val_usd = qty * cur_p
                    # Solo considerar posiciones reales operables en Binance Spot (mínimo nocional >= $5.00 USD)
                    if val_usd >= 5.0:
                        qty_safe = round(qty, 5) if c_sym == "BTC" else round(qty, 4)
                        invested_est = round(qty_safe * cur_p, 2)
                        if qty_safe > 0 and invested_est >= 5.0:
                            active_synced_symbols.add(c_sym)
                            total_crypto_invested += invested_est
                            if c_sym not in self.open_positions:
                                self.open_positions[c_sym] = {
                                    "symbol": c_sym,
                                    "name": cur_asset["name"],
                                    "broker": "BINANCE",
                                    "category": "CRYPTO",
                                    "type": cur_asset["type"],
                                    "icon": cur_asset.get("icon", "🪙"),
                                    "entry_price": cur_p,
                                    "current_price": cur_p,
                                    "quantity": qty_safe,
                                    "invested_amount": invested_est,
                                    "current_value": invested_est,
                                    "stop_loss": self.agent.learner.get_adaptive_sl_tp(c_sym, 0.018, 0.040, cur_p, cur_asset.get("resistance"), cur_asset.get("support"))["suggested_sl"],
                                    "initial_stop_loss": self.agent.learner.get_adaptive_sl_tp(c_sym, 0.018, 0.040, cur_p, cur_asset.get("resistance"), cur_asset.get("support"))["suggested_sl"],
                                    "highest_price": cur_p,
                                    "take_profit": self.agent.learner.get_adaptive_sl_tp(c_sym, 0.018, 0.040, cur_p, cur_asset.get("resistance"), cur_asset.get("support"))["suggested_tp"],
                                    "entry_time": datetime.datetime.now().strftime("%H:%M:%S"),
                                    "entry_timestamp": time.time(),
                                    "entry_confidence": 92,
                                    "reason": f"Posición activa en cartera real Binance Spot ({qty_safe:.5f} {c_sym}).",
                                    "current_pnl": 0.0,
                                    "current_pnl_percent": 0.0,
                                    "progress_to_target": 0.0
                                }
                                self.agent._add_thought(
                                    f"💼 Sincronizada cartera real Binance: Posición en {c_sym} ({qty:.5f} {c_sym} · ${invested_est:,.2f} USD). Stop-Loss protector armado.",
                                    "INFO",
                                    c_sym,
                                    icon="🪙"
                                )
                            else:
                                pos = self.open_positions[c_sym]
                                pos["quantity"] = qty_safe
                                pos["current_price"] = cur_p
                                pos["current_value"] = round(qty_safe * cur_p, 2)
                                pos["current_pnl"] = round(pos["current_value"] - pos["invested_amount"], 2)
                                pos["current_pnl_percent"] = round(((cur_p - pos["entry_price"]) / pos["entry_price"]) * 100, 2) if pos.get("entry_price") else 0.0

        # Remover cualquier posición fantasma o saldo de polvo (dust < $5.00) que no sea operable en Binance
        to_remove = []
        is_live = self.broker_wallets["BINANCE"].get("environment") == "LIVE_REAL"
        for sym, pos in list(self.open_positions.items()):
            if pos.get("category") == "CRYPTO":
                pos_val = round(pos.get("quantity", 0.0) * pos.get("current_price", 0.0), 2)
                if sym not in active_synced_symbols or pos.get("quantity", 0) <= 0:
                    to_remove.append(sym)
                elif is_live and (pos_val < 5.0 or pos.get("invested_amount", 0.0) < 5.0):
                    to_remove.append(sym)
        for sym in to_remove:
            del self.open_positions[sym]

        # Recalcular capital base del broker si estamos en MODO REAL
        if is_live:
            # En modo real, el capital total en custodia es cash real + valor de criptos reales
            total_real_equity = round(real_cash + total_crypto_invested, 2)
            vault = float(self.broker_wallets["BINANCE"].get("profit_vault", 0.0))
            if total_real_equity > 0:
                # El capital base es el saldo total real en Binance menos la bóveda de ganancias acumuladas,
                # para que (Base + Bóveda) coincida exactamente con el saldo de Binance sin inflar el NAV.
                real_base = max(0.0, round(total_real_equity - vault, 2))
                self.broker_wallets["BINANCE"]["initial_balance"] = real_base
                self.broker_config["binance_initial_balance"] = real_base
                if self.active_broker == "BINANCE":
                    self.initial_balance = real_base


    def set_execution_environment(self, env: str, custom_balance: Optional[float] = None, broker: Optional[str] = None) -> Dict[str, Any]:
        """
        Cambia de forma segura entre MODO PRÁCTICA (PAPER) y MODO DINERO REAL (LIVE_REAL)
        de forma totalmente aislada para el broker seleccionado (Alpaca o Binance).
        """
        target_b = (broker or self.active_broker).upper()

        if target_b == "ALPACA":
            if env == "LIVE_REAL":
                self.feed.alpaca.base_url = "https://api.alpaca.markets"
                conn = self.feed.alpaca.test_connection()
                if not conn.get("connected"):
                    self.feed.alpaca.base_url = "https://paper-api.alpaca.markets"
                    raw_err = conn.get('error', 'Verifica tus credenciales reales')
                    if self.feed.alpaca.api_key.startswith("PK"):
                        raw_err += " (Nota: Tu API Key comienza con 'PK', que corresponde a Alpaca Paper/Sandbox. Para operar en Modo Real de Wall Street necesitas las llaves de tu cuenta Live fondeada de Alpaca, que usualmente comienzan con 'AK')."
                    return {
                        "success": False,
                        "error": f"Error conectando a Alpaca Live: {raw_err}. Se mantiene en Modo Paper."
                    }
                self.broker_wallets["ALPACA"]["environment"] = "LIVE_REAL"
                self.broker_config["alpaca_environment"] = "LIVE_REAL"
                self.broker_config["alpaca"]["base_url"] = "https://api.alpaca.markets"
                self.broker_wallets["ALPACA"]["cash"] = float(conn.get("cash", 0.0))
                self.broker_wallets["ALPACA"]["initial_balance"] = float(conn.get("equity", 0.0))

                # LIMPIEZA DE POSICIONES SIMULADAS PREVIAS DE MODO PAPER:
                tradfi_symbols_set = {"AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "INTC", "SPY", "QQQ", "DIA"}
                for s in list(self.open_positions.keys()):
                    pos = self.open_positions[s]
                    if pos.get("broker") == "ALPACA" or pos.get("category") in ["TRADFI", "ETF"] or s in tradfi_symbols_set or pos.get("symbol") in tradfi_symbols_set:
                        del self.open_positions[s]

                # Sincronizar posiciones reales que el usuario tenga abiertas en Alpaca
                try:
                    alp_pos = self.feed.alpaca.get_positions()
                    for p in alp_pos:
                        sym = p.get("symbol", "").upper()
                        if sym:
                            self.open_positions[sym] = {
                                "symbol": sym,
                                "name": sym,
                                "broker": "ALPACA",
                                "category": "TRADFI",
                                "type": "TRADFI_STOCK",
                                "icon": "🏛️",
                                "entry_price": float(p.get("avg_entry_price", 0.0)),
                                "current_price": float(p.get("current_price", p.get("avg_entry_price", 0.0))),
                                "quantity": float(p.get("qty", 0.0)),
                                "invested_amount": float(p.get("market_value", 0.0)),
                                "current_value": float(p.get("market_value", 0.0)),
                                "stop_loss": 0.0,
                                "take_profit": 0.0,
                                "entry_time": datetime.datetime.now().strftime("%H:%M:%S"),
                                "entry_timestamp": time.time(),
                                "entry_confidence": 0.90,
                                "reason": "Posición real sincronizada desde Alpaca Custodia",
                                "current_pnl": float(p.get("unrealized_pl", 0.0)),
                                "current_pnl_percent": float(p.get("unrealized_plpc", 0.0)) * 100
                            }
                except Exception as e:
                    print(f"[ENGINE] Error sincronizando posiciones reales de Alpaca: {e}")

                # Reconciliación obligatoria de órdenes en tránsito (In-flight orders en Alpaca)
                try:
                    open_orders = self.feed.alpaca.get_open_orders()
                    if open_orders:
                        self.agent._add_thought(f"⚠️ RECONCILIACIÓN IN-FLIGHT: Detectadas {len(open_orders)} órdenes abiertas en tránsito en Alpaca.", "WARNING", icon="🔄")
                except Exception as e:
                    print(f"[ENGINE] Error reconciliando órdenes abiertas de Alpaca: {e}")

                if self.active_broker == "ALPACA":
                    self.execution_environment = "LIVE_REAL"
                    self.cash_balance = self.broker_wallets["ALPACA"]["cash"]
                    self.initial_balance = self.broker_wallets["ALPACA"]["initial_balance"]
                save_broker_config(self.broker_config)
                self.agent._add_thought(f"🔥 MODO DINERO REAL ACTIVADO en Alpaca Wall Street. Balance real en custodia: ${conn.get('equity', 0):,.2f} USD.", "WARNING", icon="🏛️")
                return {"success": True, "broker": "ALPACA", "environment": "LIVE_REAL", "equity": conn.get("equity")}
            else:
                self.feed.alpaca.base_url = "https://paper-api.alpaca.markets"
                self.broker_wallets["ALPACA"]["environment"] = "PAPER"
                self.broker_config["alpaca_environment"] = "PAPER"
                if "alpaca" in self.broker_config:
                    self.broker_config["alpaca"]["base_url"] = "https://paper-api.alpaca.markets"
                if custom_balance is not None and float(custom_balance) > 0:
                    bal_val = float(custom_balance)
                    self.broker_wallets["ALPACA"]["cash"] = bal_val
                    self.broker_wallets["ALPACA"]["initial_balance"] = bal_val
                    self.broker_config["alpaca_initial_balance"] = bal_val
                if self.active_broker == "ALPACA":
                    self.execution_environment = "PAPER"
                    self.cash_balance = self.broker_wallets["ALPACA"]["cash"]
                    self.initial_balance = self.broker_wallets["ALPACA"]["initial_balance"]
                save_broker_config(self.broker_config)
                self.agent._add_thought(f"🛡️ MODO PAPER ACTIVADO en Alpaca Wall Street. Saldo: ${self.broker_wallets['ALPACA']['cash']:,.2f} USD.", "INFO", icon="🛡️")
                return {"success": True, "broker": "ALPACA", "environment": "PAPER", "equity": self.get_broker_equity("ALPACA")}

        else: # BINANCE o Genérico
            if env == "LIVE_REAL":
                if not self.feed.binance.is_configured:
                    return {"success": False, "error": "Credenciales de Binance no configuradas."}
                acc = self.feed.binance.get_account_balances()
                if not acc.get("authenticated"):
                    return {"success": False, "error": f"Rechazado por Binance: {acc.get('error', 'Credenciales inválidas')}. Se mantiene en Modo Paper."}
                self.feed.binance.live_trading_enabled = True
                self.broker_wallets["BINANCE"]["environment"] = "LIVE_REAL"
                self.broker_config["binance_environment"] = "LIVE_REAL"
                self.broker_config["execution_environment"] = "LIVE_REAL"

                # LIMPIEZA DE POSICIONES CRIPTO PREVIAS DE MODO PAPER:
                # Al conmutar a MODO REAL, eliminamos las posiciones simuladas fantasmas,
                # pero PRESERVAMOS los datos de entrada de posiciones que ya están abiertas legítimamente en Binance.
                crypto_symbols_set = {"BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK", "NEAR"}
                real_balances = acc.get("balances", {})
                for s in list(self.open_positions.keys()):
                    pos = self.open_positions[s]
                    if pos.get("category") == "CRYPTO" or s in crypto_symbols_set or pos.get("symbol") in crypto_symbols_set:
                        asset_info = real_balances.get(s, {})
                        free_q = float(asset_info.get("free", 0.0)) + float(asset_info.get("locked", 0.0))
                        asset_obj = self.feed.get_asset(s)
                        p_val = free_q * (asset_obj["price"] if asset_obj else 0.0)
                        if p_val < 5.0:
                            # Posición simulada fantasma o polvo inoperable -> eliminar
                            del self.open_positions[s]

                self._sync_binance_wallet_positions(acc)
                b_eq = self.get_broker_equity("BINANCE")

                if self.active_broker == "BINANCE":
                    self.execution_environment = "LIVE_REAL"
                    self.cash_balance = self.broker_wallets["BINANCE"]["cash"]
                    self.initial_balance = self.broker_wallets["BINANCE"]["initial_balance"]

                save_broker_config(self.broker_config)
                self.agent._add_thought(f"🔥 MODO DINERO REAL ACTIVADO en Binance Spot. Saldo real en custodia: ${b_eq:,.2f} USD (Disponible: ${self.broker_wallets['BINANCE']['cash']:,.2f} USDT).", "WARNING", icon="🪙")
                return {"success": True, "broker": "BINANCE", "environment": "LIVE_REAL", "equity": b_eq}

            else:
                self.feed.binance.live_trading_enabled = False
                target_wallet = self.broker_wallets.get(target_b, self.broker_wallets["BINANCE"])
                target_wallet["environment"] = "PAPER"
                self.broker_config[f"{target_b.lower()}_environment"] = "PAPER"
                if target_b == "BINANCE":
                    self.broker_config["execution_environment"] = "PAPER"
                if custom_balance is not None and float(custom_balance) > 0:
                    bal_val = float(custom_balance)
                    target_wallet["cash"] = bal_val
                    target_wallet["initial_balance"] = bal_val
                    self.broker_config[f"{target_b.lower()}_initial_balance"] = bal_val
                    if target_b == "BINANCE":
                        self.broker_config["paper_initial_balance"] = bal_val
                if self.active_broker == target_b:
                    self.execution_environment = "PAPER"
                    self.cash_balance = target_wallet["cash"]
                    self.initial_balance = target_wallet["initial_balance"]
                save_broker_config(self.broker_config)
                b_name = target_wallet.get("name", target_b)
                self.agent._add_thought(f"🛡️ MODO PRÁCTICA ACTIVADO en {b_name}. Saldo de simulación: ${target_wallet['cash']:,.2f} USD.", "INFO", icon="🛡️")
                return {"success": True, "broker": target_b, "environment": "PAPER", "equity": self.get_broker_equity(target_b)}

    def get_broker_positions(self, broker: str) -> List[Dict[str, Any]]:
        b = broker.upper()
        return [
            p for p in self.open_positions.values()
            if p.get("broker", "BINANCE" if p.get("category") == "CRYPTO" else "ALPACA").upper() == b
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
        base = wallet.get("initial_balance", 0.0)
        vault = wallet.get("profit_vault", 0.0)
        unrealized = sum(p.get("current_pnl", 0.0) for p in self.get_broker_positions(b))
        return round(base + vault + unrealized, 2)

    def set_active_broker(self, broker: str) -> Dict[str, Any]:
        b = broker.upper()
        if b not in self.broker_wallets:
            return {"success": False, "error": f"Broker {broker} no soportado o no registrado"}

        self.active_broker = b
        self.broker_config["active_broker"] = b
        wallet = self.broker_wallets[b]
        
        if b == "BINANCE":
            self.operating_mode = "BINANCE_CRYPTO"
        elif b == "ALPACA":
            self.operating_mode = "ALPACA_PAPER"
        else:
            self.operating_mode = f"{b}_TRADING"

        self.execution_environment = wallet.get("environment", "PAPER")
        
        vault_key = f"{b.lower()}_profit_vault"
        init_key = f"{b.lower()}_initial_balance"
        wallet["profit_vault"] = float(self.broker_config.get(vault_key, wallet.get("profit_vault", 0.0)))
        if init_key in self.broker_config:
            wallet["initial_balance"] = float(self.broker_config[init_key])
        elif b == "BINANCE" and "paper_initial_balance" in self.broker_config:
            wallet["initial_balance"] = float(self.broker_config["paper_initial_balance"])

        if self.execution_environment == "LIVE_REAL":
            if b == "ALPACA" and self.feed.alpaca.is_configured:
                self.feed.alpaca.base_url = "https://api.alpaca.markets"
                acc = self.feed.alpaca.get_account_summary()
                if acc.get("connected"):
                    wallet["cash"] = float(acc.get("cash", 0.0))
                    alp_vault = float(wallet.get("profit_vault", 0.0))
                    total_eq = float(acc.get("equity", 0.0))
                    wallet["initial_balance"] = max(0.0, round(total_eq - alp_vault, 2))
            elif b == "BINANCE" and self.feed.binance.is_configured:
                acc = self.feed.binance.get_account_balances()
                if acc.get("authenticated"):
                    self._sync_binance_wallet_positions(acc)

        # Mantener consistencia del flag live_trading_enabled para Binance en operaciones concurrentes
        binance_is_live = (self.broker_wallets.get("BINANCE", {}).get("environment") == "LIVE_REAL")
        if self.feed.binance.is_configured:
            self.feed.binance.live_trading_enabled = binance_is_live

        self.cash_balance = wallet["cash"]
        self.initial_balance = wallet["initial_balance"]
        self.profit_target_amount = wallet.get("target_amount", self.profit_target_amount)
        self.max_loss_amount = wallet.get("max_loss_amount", self.max_loss_amount)

        self.feed.set_mode(self.operating_mode)
        self.broker_config["operating_mode"] = self.operating_mode
        save_broker_config(self.broker_config)
        
        b_name = wallet.get("name", b)
        b_icon = wallet.get("icon", "🪙" if b == "BINANCE" else "🏛️")
        self.agent._add_thought(f"🔀 Contexto cambiado a broker: {b_icon} {b_name}. Operaciones y métricas aisladas activadas.", "INFO", icon=b_icon)
        return {
            "success": True, 
            "active_broker": b, 
            "operating_mode": self.operating_mode,
            "cash": self.cash_balance,
            "equity": self.get_broker_equity(b)
        }

    def set_operating_mode(self, mode: str):
        valid_modes = [
            "UNIFIED_TRADFI_CRYPTO", 
            "TRADFI_WALLSTREET", 
            "BINANCE_CRYPTO", 
            "HYBRID", 
            "ALPACA_PAPER", 
            "SIMULATION"
        ]
        if mode in valid_modes:
            self.operating_mode = mode
            self.feed.set_mode(mode)
            self.broker_config["operating_mode"] = mode
            save_broker_config(self.broker_config)
            
            mode_names = {
                "UNIFIED_TRADFI_CRYPTO": "🌐 Multiactivo Unificado (Wall Street TradFi + Cripto 24/7)",
                "TRADFI_WALLSTREET": "🏛️ Wall Street TradFi (Acciones de EE.UU. + ETFs)",
                "BINANCE_CRYPTO": "🪙 Criptomonedas 24/7 (Binance Spot)",
                "HYBRID": "🔄 Modo Híbrido Multiactivo",
                "ALPACA_PAPER": "🟢 Wall Street Paper Trading (Alpaca)",
                "SIMULATION": "🔵 Simulador Cuantitativo 24/7"
            }
            self.agent._add_thought(
                f"🔀 Modo de Mercado: {mode_names.get(mode, mode)}",
                "INFO",
                icon="📡"
            )

    def update_broker_keys(self, alpaca_key: str = "", alpaca_secret: str = "", binance_key: str = "", binance_secret: str = ""):
        if alpaca_key or alpaca_secret:
            self.broker_config["alpaca"]["api_key"] = alpaca_key
            self.broker_config["alpaca"]["secret_key"] = alpaca_secret
            self.broker_config["alpaca"]["enabled"] = bool(alpaca_key and alpaca_secret)
        if binance_key or binance_secret:
            self.broker_config["binance"]["api_key"] = binance_key
            self.broker_config["binance"]["secret_key"] = binance_secret
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

        # Persistir en disco para que nunca se reseteen al recargar la página o reiniciar
        self.broker_config[f"{target_b.lower()}_profit_target_amount"] = target_val
        self.broker_config[f"{target_b.lower()}_max_loss_amount"] = loss_val
        self.broker_config[f"{target_b.lower()}_max_loss_enabled"] = loss_enabled
        if target_b == "BINANCE":
            self.broker_config["profit_target_amount"] = target_val
            self.broker_config["max_loss_amount"] = loss_val
            self.broker_config["max_loss_enabled"] = loss_enabled
        elif target_b == "ALPACA":
            self.broker_config["alpaca_profit_target_amount"] = target_val
            self.broker_config["alpaca_max_loss_amount"] = loss_val
            self.broker_config["alpaca_max_loss_enabled"] = loss_enabled

        self.broker_config["profit_target_enabled"] = target_enabled
        self.broker_config["max_loss_enabled"] = loss_enabled
        save_broker_config(self.broker_config)

        b_name = "Alpaca Wall Street" if target_b == "ALPACA" else "Binance Spot"
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
        msg = f"Cooldown restaurado para {symbol}" if symbol else "Todos los cooldowns han sido reiniciados."
        self.agent._add_thought(f"🔄 {msg}", "INFO", icon="✨")

    def step(self):
        market_state = self.feed.tick()

        # 1. Actualizar posiciones abiertas y gestionar Trailing Stop Adaptativo
        for sym, pos in list(self.open_positions.items()):
            asset = market_state.get(sym)
            if not asset:
                continue
            current_price = asset["price"]
            entry_price = pos["entry_price"]
            quantity = pos["quantity"]
            category = asset.get("category", "TRADFI_STOCK")
            
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

            # TRAILING STOP ADAPTATIVO POR CATEGORÍA:
            # Protege ganancias progresivamente con holgura dinámica para no asfixiar la orden
            if category in ["TRADFI_STOCK", "ETF"]:
                if pnl_pct >= 1.2:
                    secured_sl = round(pos["highest_price"] * 0.993, 2 if entry_price < 1000 else 1)
                    if pos.get("stop_loss", 0) < secured_sl:
                        pos["stop_loss"] = secured_sl
                        self.agent._add_thought(f"🔒 Trailing Stop TradFi en {sym}: Asegurando ganancia en ${secured_sl:,.2f}.", "INFO", sym, "🔒")
                elif pnl_pct >= 0.6:
                    secured_sl = round(entry_price * 1.002, 2 if entry_price < 1000 else 1)
                    if pos.get("stop_loss", 0) < secured_sl:
                        pos["stop_loss"] = secured_sl
                        self.agent._add_thought(f"🔒 Trailing Stop TradFi en {sym}: Asegurando +0.2% ganancia (${secured_sl:,.2f}).", "INFO", sym, "🔒")
                elif pnl_pct >= 0.25 and elapsed >= 20.0:
                    secured_sl = round(entry_price * 1.0005, 2 if entry_price < 1000 else 1)
                    if pos.get("stop_loss", 0) < secured_sl:
                        pos["stop_loss"] = secured_sl
                        self.agent._add_thought(f"🛡️ Break-Even TradFi en {sym}: Escudo en ${secured_sl:,.2f} para eliminar riesgo (Cero Pérdidas).", "INFO", sym, "🛡️")
            else:
                # Cripto: Mayor rango dinámico de volatilidad (evita cierre prematuro en los primeros segundos)
                if pnl_pct >= 2.0:
                    secured_sl = round(pos["highest_price"] * 0.988, 2 if entry_price < 1000 else 1)
                    if pos.get("stop_loss", 0) < secured_sl:
                        pos["stop_loss"] = secured_sl
                        self.agent._add_thought(f"🔒 Trailing Stop Cripto en {sym}: Asegurando ganancia en ${secured_sl:,.2f}.", "INFO", sym, "🔒")
                elif pnl_pct >= 1.2:
                    secured_sl = round(entry_price * 1.005, 2 if entry_price < 1000 else 1)
                    if pos.get("stop_loss", 0) < secured_sl:
                        pos["stop_loss"] = secured_sl
                        self.agent._add_thought(f"🔒 Trailing Stop Cripto en {sym}: Asegurando +0.5% ganancia (${secured_sl:,.2f}).", "INFO", sym, "🔒")
                elif pnl_pct >= 0.70 and elapsed >= 25.0:
                    secured_sl = round(entry_price * 1.001, 2 if entry_price < 1000 else 1)
                    if pos.get("stop_loss", 0) < secured_sl:
                        pos["stop_loss"] = secured_sl
                        self.agent._add_thought(f"🛡️ Break-Even Cripto en {sym}: Escudo en ${secured_sl:,.2f} protegiendo inversión (Cero Pérdidas).", "INFO", sym, "🛡️")
            
            tp = pos.get("take_profit", entry_price * 1.04)
            if tp > entry_price:
                pct_to_tp = min(100.0, max(0.0, ((current_price - entry_price) / (tp - entry_price)) * 100))
            else:
                pct_to_tp = 0.0
            pos["progress_to_target"] = round(pct_to_tp, 1)

        # 2 & 3. CIRCUIT BREAKERS MULTIBROKER CONCURRENTES (EVALUADOS INDEPENDIENTEMENTE POR CADA BROKER)
        for b_id, b_wal in list(self.broker_wallets.items()):
            b_equity = self.get_broker_equity(b_id)
            b_init_bal = b_wal.get("initial_balance", 100.0)
            b_profit = round(b_equity - b_init_bal, 2)

            # Meta de ganancia por broker
            b_target_amt = b_wal.get("target_amount", self.profit_target_amount)
            if self.profit_target_enabled and b_profit >= b_target_amt and not b_wal.get("target_alerted", False):
                b_wal["target_alerted"] = True
                self.agent._add_thought(
                    f"🏆 ¡OBJETIVO DE GANANCIA ALCANZADO [{b_wal.get('icon','💼')} {b_wal.get('name', b_id)}] (+${b_profit:,.2f} USD)! "
                    f"Ganancias protegidas e intocables en la Bóveda (${b_wal.get('profit_vault', 0.0):,.2f} USD). "
                    f"El motor continúa operando con el Capital Base de ${b_wal['initial_balance']:,.2f} USD.",
                    "TRADE_WIN",
                    icon="🎯"
                )

            # Límite defensivo por broker (Tolerancia Cero y Límite Máximo)
            b_max_loss = b_wal.get("max_loss_amount", self.max_loss_amount)
            b_loss_enabled = b_wal.get("loss_enabled", self.max_loss_enabled)
            
            is_b_loss_triggered = False
            if b_loss_enabled and not b_wal.get("loss_limit_reached", False):
                if b_max_loss == 0.0 and b_profit < 0.0:
                    is_b_loss_triggered = True
                elif b_max_loss > 0.0 and b_profit <= -b_max_loss:
                    is_b_loss_triggered = True

            if is_b_loss_triggered:
                # Cierra exclusivamente las posiciones de este broker para proteger su capital
                for sym in list(self.open_positions.keys()):
                    pos = self.open_positions[sym]
                    pos_b = pos.get("broker", "BINANCE" if pos.get("category") == "CRYPTO" else "ALPACA")
                    if pos_b == b_id:
                        asset = self.feed.get_asset(sym)
                        if asset:
                            decision = {"decision": "EMERGENCY_SELL", "reason_simple": f"Escudo Defensivo [{b_wal.get('name', b_id)}]: Tolerancia Cero Activada"}
                            self._execute_sell(sym, asset, decision)
                b_wal["loss_limit_reached"] = False
                self.agent._add_thought(
                    f"🛡️ ESCUDO ACTIVADO [{b_wal.get('icon','💼')} {b_wal.get('name', b_id)}]: Tolerancia a pérdida disparada (${b_profit:,.2f} USD). "
                    f"Posiciones cerradas para blindar capital base en ${b_wal['initial_balance']:,.2f} USD.",
                    "WARNING",
                    icon="🛡️"
                )

        # 4. Sincronización continua e independiente de TODOS los brokers en segundo plano 24/7
        if not hasattr(self, "_last_broker_sync"):
            self._last_broker_sync = {}

        now_sync = time.time()
        for b_id, b_wal in list(self.broker_wallets.items()):
            if b_wal.get("environment") == "LIVE_REAL":
                if b_id == "BINANCE" and self.feed.binance.is_configured:
                    self.feed.binance.live_trading_enabled = True
                    if (now_sync - self._last_broker_sync.get("BINANCE", 0.0)) > 3.0:
                        self._last_broker_sync["BINANCE"] = now_sync
                        acc = self.feed.binance.get_account_balances()
                        if acc.get("authenticated"):
                            self._sync_binance_wallet_positions(acc)
                            if self.active_broker == "BINANCE" and self.initial_balance <= 1.0 and (self.cash_balance + self.get_invested_capital()) > 1.0:
                                self.initial_balance = round(self.cash_balance + self.get_invested_capital(), 2)
                elif b_id == "ALPACA" and self.feed.alpaca.is_configured:
                    if (now_sync - self._last_broker_sync.get("ALPACA", 0.0)) > 10.0:
                        self._last_broker_sync["ALPACA"] = now_sync
                        acc = self.feed.alpaca.get_account_summary()
                        if acc.get("connected"):
                            b_wal["cash"] = float(acc.get("cash", 0.0))
                            alp_vault = float(b_wal.get("profit_vault", 0.0))
                            total_eq = float(acc.get("equity", b_wal["initial_balance"]))
                            b_wal["initial_balance"] = max(0.0, round(total_eq - alp_vault, 2))

        # 5. Escaneo y Operación Autónoma Continua 24/7
        if self.is_running:
            self._evaluate_and_trade(market_state)

        # 6. Snapshot de equity
        self._record_equity_snapshot()

    def _evaluate_and_trade(self, market_state: Dict[str, Any]):
        # A. Evaluar salidas de posiciones abiertas para TODOS los brokers
        for sym, pos in list(self.open_positions.items()):
            asset = market_state.get(sym)
            if not asset:
                continue
            decision_data = self.agent.evaluate_asset(asset, self.open_positions)
            
            # Protección de Tiempo Mínimo de Maduración (35 segundos para consolidación)
            entry_ts = pos.get("entry_timestamp", 0)
            elapsed = time.time() - entry_ts if entry_ts > 0 else 999
            
            # Durante los primeros 30s se evalúa el SL inicial para no ser asfixiado por micro-ruido de segundos
            active_sl = pos.get("initial_stop_loss", pos.get("stop_loss", 0)) if elapsed < 30.0 else pos.get("stop_loss", 0)
            is_hard_sl = asset["price"] <= active_sl
            is_hard_tp = asset["price"] >= pos.get("take_profit", 999999)
            
            if elapsed < 35.0 and not is_hard_sl and not is_hard_tp:
                continue

            if is_hard_sl or is_hard_tp or decision_data["decision"] in ["SELL", "SELL_STOP_LOSS", "SELL_TAKE_PROFIT"] or "SELL" in decision_data.get("action_type", ""):
                self._execute_sell(sym, asset, decision_data)

        # B. OPERACIÓN CONCURRENTE MULTIBROKER (TODOS LOS BROKERS OPERAN AL MISMO TIEMPO):
        min_cash = 5.0
        now_ts = time.time()

        for b_id, wallet in list(self.broker_wallets.items()):
            if not wallet.get("is_running", True):
                continue
            if wallet.get("target_reached") or wallet.get("loss_limit_reached"):
                continue

            allowed_categories = wallet.get("allowed_categories", ["CRYPTO"] if b_id == "BINANCE" else ["TRADFI_STOCK", "ETF"])
            broker_equity = self.get_broker_equity(b_id)
            max_positions = 2 if broker_equity <= 50.0 else 5
            broker_positions = self.get_broker_positions(b_id)

            if len(broker_positions) >= max_positions or wallet.get("cash", 0.0) < min_cash:
                continue

            candidates = []
            for sym, asset in market_state.items():
                if sym in self.open_positions:
                    continue
                if allowed_categories and asset.get("category") not in allowed_categories:
                    continue
                
                # Descartar activos en enfriamiento del agente o en enfriamiento post-salida reciente (180s)
                if self.agent.learner.is_asset_in_cooldown(sym):
                    continue
                if (now_ts - self.last_exit_times.get(sym, 0)) < 180.0:
                    continue

                decision_data = self.agent.evaluate_asset(asset, self.open_positions)
                if decision_data["decision"] == "BUY" and decision_data["confidence"] >= 80:
                    volatility_weight = asset.get("volatility", 0.005) * 1000
                    exp_boost = self.agent.learner.get_asset_confidence_boost(sym)
                    priority_score = decision_data["confidence"] * exp_boost * (1.0 + volatility_weight * 0.5)
                    candidates.append((priority_score, sym, asset, decision_data))

            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                best_score, best_sym, best_asset, best_decision = candidates[0]
                self._execute_buy(best_sym, best_asset, best_decision, broker_id=b_id)

    def _execute_buy(self, symbol: str, asset: Dict[str, Any], decision_data: Dict[str, Any], broker_id: Optional[str] = None):
        category = asset.get("category", "TRADFI_STOCK")
        broker_id = (broker_id or self.active_broker).upper()
        wallet = self.broker_wallets.get(broker_id, self.broker_wallets["BINANCE"])
        # Capital disponible para operar: SOLO se trabaja con el capital inicial operativo base.
        # Las ganancias acumuladas en la bóveda están 100% blindadas e intocables.
        current_invested = sum(p["invested_amount"] for p in self.get_broker_positions(broker_id))
        max_operable_cash = max(0.0, wallet["initial_balance"] - current_invested)
        available_cash = min(wallet["cash"], max_operable_cash)

        kelly_pct = decision_data.get("budget_percent", 20.0)
        effective_pct = min(kelly_pct, 30.0)

        is_broker_live = (wallet.get("environment") == "LIVE_REAL")
        min_trade = 6.0 if (broker_id == "BINANCE" and is_broker_live) else 5.0
        if available_cash <= 35.0:
            target_amount = round(min(available_cash * 0.40, 10.0), 2)
            target_amount = max(min_trade, target_amount)
            if target_amount > available_cash:
                target_amount = round(available_cash * 0.90, 2)
        elif available_cash <= 500.0:
            target_amount = max(min_trade, available_cash * (effective_pct / 100.0))
            target_amount = round(min(target_amount, available_cash * 0.35), 2)
        else:
            target_amount = round(max(min_trade, min(available_cash * 0.05, 5000.0)), 2)

        if target_amount < min_trade or target_amount > available_cash:
            return

        price = asset["price"]
        if price < 1.0:
            quantity = round(target_amount / price, 2)
        elif price < 100.0:
            quantity = round(target_amount / price, 4)
        else:
            quantity = round(target_amount / price, 4 if broker_id == "ALPACA" else 5)

        actual_investment = round(quantity * price, 2)
        if actual_investment > available_cash:
            quantity = round((available_cash * 0.98) / price, 4 if price >= 100.0 else 2)
            actual_investment = round(quantity * price, 2)

        if actual_investment <= 0 or actual_investment > available_cash:
            return

        if broker_id == "BINANCE" and is_broker_live and actual_investment < 6.0:
            return

        if broker_id == "ALPACA" and actual_investment < 1.0:
            return

        # Verificación con RiskManager: Cupos, Drawdown Diario y Blindaje FINRA 4210 (PDT)
        is_tradfi = (broker_id == "ALPACA" or category in ["TRADFI", "ETF"])
        equity_now = self.get_broker_equity(broker_id)
        if hasattr(self, "risk_manager"):
            if not self.risk_manager.can_open_trade(
                risk_amount=actual_investment * 0.02,
                current_equity=equity_now,
                is_margin_account=True,
                is_tradfi=is_tradfi
            ):
                if is_tradfi and self.risk_manager.is_pdt_restricted(current_equity=equity_now):
                    self.agent._add_thought(f"🛡️ ESCUDO FINRA 4210 (PDT): Entrada en {symbol} prevenida para proteger la cuenta de suspensión por Pattern Day Trader (< $25k USD).", "WARNING", symbol, "⚠️")
                return

        wallet["cash"] = round(wallet["cash"] - actual_investment, 2)
        if broker_id == self.active_broker:
            self.cash_balance = wallet["cash"]

        stop_loss = decision_data.get("stop_loss", round(price * 0.975, 2))
        take_profit = decision_data.get("take_profit", round(price * 1.045, 2))

        position = {
            "symbol": symbol,
            "name": asset["name"],
            "broker": broker_id,
            "category": category,
            "type": asset["type"],
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
            "entry_time": datetime.datetime.now().strftime("%H:%M:%S"),
            "entry_timestamp": time.time(),
            "entry_confidence": decision_data["confidence"],
            "reason": decision_data["reason_simple"],
            "current_pnl": 0.0,
            "current_pnl_percent": 0.0,
            "progress_to_target": 0.0
        }

        # Enrutamiento de orden real en Binance (Autónomo para cada broker)
        if broker_id == "BINANCE" and is_broker_live:
            self.feed.binance.live_trading_enabled = True
            pair = asset.get("binance_pair", f"{symbol}USDT")
            real_res = self.feed.binance.create_market_order(pair, "BUY", quantity=quantity, quote_order_qty=actual_investment, force_live=True)
            if real_res.get("success"):
                data = real_res.get("data", {})
                position["broker_order_id"] = data.get("orderId")
                exec_qty = float(data.get("executedQty", 0.0))
                cumm_quote = float(data.get("cummulativeQuoteQty", 0.0))
                if exec_qty > 0 and cumm_quote > 0:
                    real_fill_price = round(cumm_quote / exec_qty, 4 if exec_qty < 1000 else 2)
                    position["quantity"] = exec_qty
                    position["entry_price"] = real_fill_price
                    position["current_price"] = real_fill_price
                    position["invested_amount"] = round(cumm_quote, 2)
                    sl_ratio = (stop_loss / price) if price > 0 else 0.985
                    tp_ratio = (take_profit / price) if price > 0 else 1.020
                    position["stop_loss"] = round(real_fill_price * sl_ratio, 2)
                    position["take_profit"] = round(real_fill_price * tp_ratio, 2)
                self.agent._add_thought(f"🔥 ORDEN REAL BINANCE: Compra ejecutada en Spot de {position['quantity']} {symbol} por ${position['invested_amount']:.2f} USDT.", "WARNING", symbol, "⚡")
            else:
                self.agent._add_thought(f"⚠️ Error orden real Binance: {real_res.get('error')}", "WARNING", symbol, "🛑")
                wallet["cash"] = round(wallet["cash"] + actual_investment, 2)
                if broker_id == self.active_broker:
                    self.cash_balance = wallet["cash"]
                return

        # Enrutamiento de orden en Alpaca (Paper o Real) con idempotencia client_order_id
        if broker_id == "ALPACA" and self.feed.alpaca.is_configured:
            order_res = self.feed.alpaca.submit_order(symbol, quantity, "buy")
            if order_res.get("success"):
                cid = order_res.get("client_order_id", "")
                position["broker_order_id"] = cid
                self.agent._add_thought(f"🏛️ ORDEN ALPACA ENVIADA: Compra de {quantity} {symbol} en Wall Street (ID: {cid}).", "INFO", symbol, "⚡")
            else:
                self.agent._add_thought(f"⚠️ Error orden Alpaca: {order_res.get('error')}", "WARNING", symbol, "🛑")
                if self.broker_wallets.get("ALPACA", {}).get("environment") == "LIVE_REAL":
                    wallet["cash"] = round(wallet["cash"] + actual_investment, 2)
                    if broker_id == self.active_broker:
                        self.cash_balance = wallet["cash"]
                    return

        self.open_positions[symbol] = position
        if hasattr(self, "risk_manager"):
            self.risk_manager.register_trade_open()

        cat_badge = "🏛️ Alpaca" if broker_id == "ALPACA" else "🪙 Binance"
        self.agent._add_thought(
            f"🛒 ¡COMPRADO [{cat_badge}]! {quantity} {symbol} ({asset['name']}) por ${actual_investment:,.2f} USD. Kelly: {kelly_pct}% | Meta: ${take_profit:,.2f} | Escudo: ${stop_loss:,.2f}.",
            "TRADE_BUY",
            symbol,
            icon="🟢"
        )

    def _execute_sell(self, symbol: str, asset: Dict[str, Any], decision_data: Dict[str, Any]):
        if symbol not in self.open_positions:
            return
        
        pos = self.open_positions.pop(symbol)
        exit_price = asset["price"]
        quantity = pos["quantity"]
        exit_value = round(quantity * exit_price, 2)
        invested = pos["invested_amount"]
        pnl = round(exit_value - invested, 2)
        entry_p = pos.get("entry_price", exit_price)
        pnl_pct = round(((exit_price - entry_p) / entry_p) * 100, 2) if entry_p > 0 else 0.0
        broker_id = pos.get("broker", self.active_broker)
        wallet = self.broker_wallets.get(broker_id, self.broker_wallets["BINANCE"])
        b_icon = wallet.get("icon", "🪙" if broker_id == "BINANCE" else "🏛️")
        broker_badge = f"{b_icon} {wallet.get('name', broker_id)}"

        # Separación estricta de ganancias:
        # El principal retorna al efectivo operativo; la ganancia neta se asegura en la Bóveda y NO se toca.
        if pnl > 0:
            wallet["cash"] = round(wallet["cash"] + invested, 2)
            wallet["profit_vault"] = round(wallet.get("profit_vault", 0.0) + pnl, 2)
            self.broker_config[f"{broker_id.lower()}_profit_vault"] = wallet["profit_vault"]
            save_broker_config(self.broker_config)
        else:
            wallet["cash"] = round(wallet["cash"] + exit_value, 2)

        if broker_id == self.active_broker:
            self.cash_balance = wallet["cash"]

        # Enrutamiento de orden de venta real en Binance (Autónomo para cada broker)
        is_broker_live = (wallet.get("environment") == "LIVE_REAL")
        if broker_id == "BINANCE" and is_broker_live:
            self.feed.binance.live_trading_enabled = True
            pair = asset.get("binance_pair", f"{symbol}USDT")
            real_res = self.feed.binance.create_market_order(pair, "SELL", quantity, force_live=True)
            if real_res.get("success"):
                self.agent._add_thought(f"🔥 VENTA REAL BINANCE: Vendidos {quantity} {symbol} en Spot.", "WARNING", symbol, "⚡")
            else:
                err_msg = str(real_res.get('error', ''))
                if "-2010" in err_msg or "Sin saldo disponible" in err_msg or "insufficient balance" in err_msg.lower():
                    self.agent._add_thought(f"ℹ️ Posición de {symbol} purgada: No existe saldo físico libre en Binance Spot.", "INFO", symbol, "🧹")
                    self._sync_binance_wallet_positions(self.feed.binance.get_account_balances())
                    return
                elif "-1013" in err_msg or "NOTIONAL" in err_msg or real_res.get("is_dust") or "Filter failure" in err_msg:
                    self.agent._add_thought(
                        f"ℹ️ Posición de {symbol} archivada: El valor remanente (${exit_value:.2f} USD) es inferior al mínimo de $5.00 USD exigido por Binance Spot. Los tokens permanecen seguros en tu billetera de Binance.",
                        "INFO", symbol, "🪙"
                    )
                    self._sync_binance_wallet_positions(self.feed.binance.get_account_balances())
                    return
                else:
                    self.agent._add_thought(f"⚠️ Venta real en Binance no completada ({err_msg}). Posición mantenida para reintento.", "WARNING", symbol, "🛑")
                    self.open_positions[symbol] = pos
                    if pnl > 0:
                        wallet["cash"] = round(wallet["cash"] - invested, 2)
                        wallet["profit_vault"] = round(wallet.get("profit_vault", 0.0) - pnl, 2)
                    else:
                        wallet["cash"] = round(wallet["cash"] - exit_value, 2)
                    if broker_id == self.active_broker:
                        self.cash_balance = wallet["cash"]
                    return


        # Enrutamiento de venta en Alpaca
        if broker_id == "ALPACA" and self.feed.alpaca.is_configured:
            alp_res = self.feed.alpaca.submit_order(symbol, quantity, "sell")
            if not alp_res.get("success"):
                err_msg = str(alp_res.get("error", ""))
                if "sin acciones" in err_msg.lower() or "insufficient" in err_msg.lower() or "not found" in err_msg.lower() or "position" in err_msg.lower():
                    self.agent._add_thought(f"ℹ️ Posición de {symbol} purgada: No existen acciones libres en Alpaca Wall Street.", "INFO", symbol, "🧹")
                    return
                else:
                    self.agent._add_thought(f"⚠️ Venta en Alpaca no completada ({err_msg}). Posición mantenida para reintento.", "WARNING", symbol, "🛑")
                    self.open_positions[symbol] = pos
                    if pnl > 0:
                        wallet["cash"] = round(wallet["cash"] - invested, 2)
                        wallet["profit_vault"] = round(wallet.get("profit_vault", 0.0) - pnl, 2)
                    else:
                        wallet["cash"] = round(wallet["cash"] - exit_value, 2)
                    if broker_id == self.active_broker:
                        self.cash_balance = wallet["cash"]
                    return

        trade_record = {
            "symbol": symbol,
            "name": pos["name"],
            "broker": broker_id,
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
            "exit_reason": decision_data.get("reason_simple", "Venta ejecutada"),
            "exit_type": decision_data.get("decision", "SELL"),
            "success": pnl > 0
        }
        self.journal.record_trade(trade_record)
        self.agent.record_trade_result(trade_record)
        self.last_exit_times[symbol] = time.time()
        if hasattr(self, "risk_manager"):
            self.risk_manager.register_trade_close(pnl, symbol=symbol, is_intraday=True)

        if pnl > 0:
            self.agent._add_thought(
                f"💰 ¡VENDIDO CON GANANCIA [{broker_badge}]! {symbol} cerrado a ${exit_price:,.2f}. Retorno: +${pnl:,.2f} USD (+{pnl_pct:.2f}%). "
                f"🔒 Ganancia depositada en la Bóveda (Total protegido: ${wallet['profit_vault']:,.2f} USD). Capital operativo base intacto.",
                "TRADE_WIN",
                symbol,
                icon="💵"
            )
        else:
            self.agent._add_thought(
                f"🛡️ STOP-LOSS EJECUTADO [{broker_badge}]: {symbol} cerrado a ${exit_price:,.2f}. Pérdida mínima controlada: -${abs(pnl):,.2f} USD ({pnl_pct:.2f}%). Bóveda de ganancias protegida.",
                "TRADE_LOSS",
                symbol,
                icon="🛑"
            )

    def emergency_close_all(self):
        for sym in list(self.open_positions.keys()):
            asset = self.feed.get_asset(sym)
            if asset:
                decision = {
                    "decision": "EMERGENCY_SELL",
                    "reason_simple": "Cierre Inmediato de Seguridad / Meta o Límite alcanzado"
                }
                self._execute_sell(sym, asset, decision)

    def toggle_pause(self) -> bool:
        if self.target_reached or self.loss_limit_reached:
            self.initial_balance = self.get_total_equity()
            self.target_reached = False
            self.loss_limit_reached = False
            self.is_running = True
            self.agent._add_thought(
                f"▶️ Nueva Sesión Cuantitativa: Capital base en ${self.initial_balance:,.2f} USD. Buscando meta de +${self.profit_target_amount:,.2f} USD.",
                "INFO",
                icon="🚀"
            )
            return self.is_running

        self.is_running = not self.is_running
        status = "REANUDADO" if self.is_running else "PAUSADO"
        icon = "▶️" if self.is_running else "⏸️"
        self.agent._add_thought(f"{icon} Agente {status} por el usuario.", "INFO", icon=icon)
        return self.is_running

    def get_state(self) -> Dict[str, Any]:
        active_b = self.active_broker
        wallet = self.broker_wallets.get(active_b, self.broker_wallets["BINANCE"])
        
        # Posiciones activas aisladas por broker
        active_positions = self.get_broker_positions(active_b)
        invested = sum(pos["invested_amount"] for pos in active_positions)
        unrealized_pnl = sum(pos.get("current_pnl", 0.0) for pos in active_positions)
        cash_avail = wallet["cash"]
        total_equity = self.get_broker_equity(active_b)
        initial_bal = wallet["initial_balance"]
        
        realized_stats = self.journal.get_statistics(broker=active_b)
        completed_trades = self.journal.get_trades(35, broker=active_b)
        
        vault_val = round(wallet.get("profit_vault", 0.0), 2)
        total_profit = round(vault_val + unrealized_pnl, 2)
        total_profit_pct = round((total_profit / initial_bal) * 100, 2) if initial_bal > 0 else 0.0

        if self.is_running:
            status_text = "OPERANDO EN VIVO (24/7)"
        elif self.target_reached:
            status_text = "🏆 META DE GANANCIA LOGRADA (DETENIDO)"
        elif self.loss_limit_reached:
            status_text = "🛑 LÍMITE PÉRDIDA ALCANZADO (DETENIDO)"
        else:
            status_text = "EN PAUSA"

        # Filtrado estricto por broker: SOLO activos permitidos para este broker (Cero mezcla)
        market_radar = []
        target_cat = ["CRYPTO"] if active_b == "BINANCE" else ["TRADFI_STOCK", "ETF"]
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

        alpaca_status = self.feed.alpaca.test_connection() if self.feed.alpaca.is_configured else {"connected": False, "status": "NO CONFIGURADO"}
        binance_status = self.feed.binance.test_connection()
        learning_summary = self.agent.learner.get_learning_summary()

        brokers_dict = {}
        for b_id, b_wal in self.broker_wallets.items():
            if b_id == "BINANCE":
                is_conn = binance_status.get("connected", True)
                status_lbl = binance_status.get("status", "FEED PÚBLICO ACTIVO")
                cat_tag = "Cripto 24/7"
            elif b_id == "ALPACA":
                is_conn = alpaca_status.get("connected", False)
                status_lbl = "CONECTADO A IEX" if is_conn else "NO CONFIGURADO"
                cat_tag = "Wall Street TradFi"
            else:
                is_conn = True
                status_lbl = "CONECTADO"
                cat_tag = b_wal.get("category", "Trading 24/7")

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
                "profit_vault": round(b_wal.get("profit_vault", 0.0), 2),
                "initial_balance": round(b_wal.get("initial_balance", 0.0), 2),
                "positions_count": len(self.get_broker_positions(b_id))
            }

        return {
            "system_status": {
                "is_running": self.is_running,
                "status_text": status_text,
                "active_broker": active_b,
                "operating_mode": self.operating_mode,
                "execution_environment": self.execution_environment,
                "paper_initial_balance": initial_bal,
                "active_assets_count": len(market_radar),
                "profit_target_enabled": self.profit_target_enabled,
                "profit_target_amount": wallet.get("target_amount", self.profit_target_amount),
                "target_reached": self.target_reached,
                "max_loss_enabled": self.max_loss_enabled,
                "max_loss_amount": wallet.get("max_loss_amount", self.max_loss_amount),
                "loss_limit_reached": self.loss_limit_reached,
                "brokers": brokers_dict,
                "broker_connections": {
                    "alpaca": alpaca_status,
                    "binance": binance_status
                }
            },
            "financial_summary": {
                "total_equity": total_equity,
                "cash_available": cash_avail,
                "invested_capital": round(invested, 2),
                "initial_balance": initial_bal,
                "operating_capital_base": initial_bal,
                "profit_vault": round(wallet.get("profit_vault", 0.0), 2),
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
            "agent_thoughts": [
                t for t in self.agent.get_thoughts(50)
                if ("Binance" if active_b == "ALPACA" else "Alpaca") not in t.get("message", "")
            ][:30] or self.agent.get_thoughts(25),
            "equity_history": self.equity_history
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
        b = (broker or self.active_broker).upper()
        wallet = self.broker_wallets.get(b)
        if not wallet:
            return {"success": False, "error": f"Broker {b} no encontrado"}
        
        current_vault = wallet.get("profit_vault", 0.0)
        if current_vault <= 0:
            return {"success": False, "error": "No hay ganancias acumuladas en la bóveda para transferir"}
        
        transfer_amount = current_vault if (amount is None or amount <= 0) else min(current_vault, round(float(amount), 2))
        
        wallet["profit_vault"] = round(wallet["profit_vault"] - transfer_amount, 2)
        wallet["initial_balance"] = round(wallet["initial_balance"] + transfer_amount, 2)
        wallet["cash"] = round(wallet["cash"] + transfer_amount, 2)
        
        # Persistencia unificada para cualquier broker
        self.broker_config[f"{b.lower()}_profit_vault"] = wallet["profit_vault"]
        self.broker_config[f"{b.lower()}_initial_balance"] = wallet["initial_balance"]
        if b == "BINANCE":
            self.broker_config["paper_initial_balance"] = wallet["initial_balance"]
            self.broker_config["binance_profit_vault"] = wallet["profit_vault"]
        elif b == "ALPACA":
            self.broker_config["alpaca_initial_balance"] = wallet["initial_balance"]
            self.broker_config["alpaca_profit_vault"] = wallet["profit_vault"]
            
        save_broker_config(self.broker_config)
        
        if b == self.active_broker:
            self.initial_balance = wallet["initial_balance"]
            self.cash_balance = wallet["cash"]
            
        b_name = wallet.get("name", b)
        self.agent._add_thought(
            f"💼 BÓVEDA TRANSFERIDA A CAPITAL [{b_name}]: Se transfirieron ${transfer_amount:,.2f} USD de ganancias acumuladas al Capital Operativo. "
            f"Nueva base operativa: ${wallet['initial_balance']:,.2f} USD. Bóveda restante: ${wallet['profit_vault']:,.2f} USD.",
            "INFO",
            icon="💼"
        )
        return {
            "success": True,
            "broker": b,
            "transferred_amount": transfer_amount,
            "new_initial_balance": wallet["initial_balance"],
            "new_cash": wallet["cash"],
            "remaining_vault": wallet["profit_vault"]
        }

    def harvest_vault_profits(self, broker: Optional[str] = None) -> Dict[str, Any]:
        """
        Cierra todas las posiciones abiertas que tengan ganancia positiva (> 0)
        para consolidar y trasladar de inmediato sus ganancias a la Bóveda protegida.
        El principal invertido regresa al efectivo operativo disponible para seguir operando.
        """
        target_b = (broker or self.active_broker).upper()
        closed = []
        total_harvested = 0.0

        for sym in list(self.open_positions.keys()):
            pos = self.open_positions[sym]
            pos_b = pos.get("broker", "BINANCE" if pos.get("category") == "CRYPTO" else "ALPACA")
            if target_b and pos_b != target_b:
                continue
            
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

        wallet = self.broker_wallets.get(target_b, self.broker_wallets.get(self.active_broker, {}))
        return {
            "success": True,
            "broker": target_b,
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
            "category": asset.get("category", "TRADFI_STOCK"),
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
        """
        Registra y activa un nuevo broker en el motor cuantitativo.
        Queda operando inmediatamente de forma simultánea con todos los demás brokers 24/7.
        """
        b = broker_id.upper().strip()
        broker_presets = {
            "BYBIT": {"name": "Bybit Exchange", "icon": "⚡", "category": "CRYPTO", "allowed": ["CRYPTO"], "target": 2000.0, "max_loss": 0.0},
            "IBKR": {"name": "Interactive Brokers", "icon": "🌐", "category": "TRADFI", "allowed": ["TRADFI_STOCK", "ETF"], "target": 5000.0, "max_loss": 0.0},
            "OKX": {"name": "OKX Exchange", "icon": "💎", "category": "CRYPTO", "allowed": ["CRYPTO"], "target": 2000.0, "max_loss": 0.0},
            "IQOPTION": {"name": "IQ Option", "icon": "📊", "category": "TRADFI", "allowed": ["TRADFI_STOCK", "ETF"], "target": 1500.0, "max_loss": 0.0},
            "COINBASE": {"name": "Coinbase Pro", "icon": "🔵", "category": "CRYPTO", "allowed": ["CRYPTO"], "target": 2500.0, "max_loss": 0.0},
            "KRAKEN": {"name": "Kraken Spot", "icon": "🐙", "category": "CRYPTO", "allowed": ["CRYPTO"], "target": 2000.0, "max_loss": 0.0}
        }
        preset = broker_presets.get(b, {
            "name": f"{b} Broker",
            "icon": "💼",
            "category": "CRYPTO" if any(c in b for c in ["CRIP", "BIT", "COIN"]) else "TRADFI",
            "allowed": ["CRYPTO"] if any(c in b for c in ["CRIP", "BIT", "COIN"]) else ["TRADFI_STOCK", "ETF"],
            "target": 3000.0,
            "max_loss": 0.0
        })

        init_bal = max(10.0, float(initial_balance))
        wallet_entry = {
            "id": b,
            "name": preset["name"],
            "icon": preset["icon"],
            "category": preset["category"],
            "allowed_categories": preset["allowed"],
            "environment": "PAPER",
            "initial_balance": init_bal,
            "cash": init_bal,
            "profit_vault": 0.0,
            "target_amount": preset["target"],
            "max_loss_amount": preset["max_loss"],
            "target_reached": False,
            "loss_limit_reached": False,
            "is_running": True,
            "api_key": api_key,
            "secret_key": secret_key
        }

        self.broker_wallets[b] = wallet_entry

        if "custom_brokers" not in self.broker_config:
            self.broker_config["custom_brokers"] = {}
        self.broker_config["custom_brokers"][b] = wallet_entry
        self.broker_config[f"{b.lower()}_initial_balance"] = init_bal
        self.broker_config[f"{b.lower()}_profit_vault"] = 0.0
        save_broker_config(self.broker_config)

        self.agent._add_thought(
            f"🚀 ¡NUEVO BROKER CONECTADO EN VIVO! [{preset['icon']} {preset['name']}]: "
            f"Iniciado con ${init_bal:,.2f} USD. Operando de inmediato de forma simultánea con los demás brokers 24/7.",
            "SUCCESS",
            icon="🚀"
        )

        return {
            "success": True,
            "broker": b,
            "name": preset["name"],
            "icon": preset["icon"],
            "initial_balance": init_bal,
            "message": f"Broker {preset['name']} conectado y operando simultáneamente 24/7."
        }
