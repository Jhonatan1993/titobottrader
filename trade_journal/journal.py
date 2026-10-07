import os
import json
import csv
import datetime
from typing import List, Dict, Any, Optional

class TradeJournal:
    """
    Registro, bitácora y persistencia en disco de todas las operaciones realizadas por el Agente.
    Guarda automáticamente cada operación en formato JSON y CSV para análisis histórico.
    """
    def __init__(self, storage_dir: str = "data"):
        self.storage_dir = storage_dir
        self.json_file = os.path.join(storage_dir, "trades_history.json")
        self.csv_file = os.path.join(storage_dir, "trades_history.csv")
        self.trades: List[Dict[str, Any]] = []
        
        os.makedirs(storage_dir, exist_ok=True)
        self._load_existing_trades()

    def _load_existing_trades(self):
        """Carga el historial guardado en disco si existe."""
        if os.path.exists(self.json_file):
            try:
                with open(self.json_file, "r", encoding="utf-8") as f:
                    self.trades = json.load(f)
            except Exception as e:
                print(f"Nota: No se pudo cargar historial previo: {e}")
                self.trades = []

    def _save_to_disk(self):
        """Guarda todas las operaciones en JSON y CSV de forma permanente."""
        try:
            # 1. Guardar en JSON
            with open(self.json_file, "w", encoding="utf-8") as f:
                json.dump(self.trades, f, indent=2, ensure_ascii=False)
            
            # 2. Guardar en CSV para abrir en Excel o Google Sheets
            if self.trades:
                keys = ["id", "broker", "category", "environment", "symbol", "name", "type", "quantity", "entry_price", "exit_price", 
                        "invested_amount", "pnl", "pnl_percent", "result", "reason", "opened_at", "closed_at", "duration"]
                with open(self.csv_file, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
                    writer.writeheader()
                    writer.writerows(self.trades)
        except Exception as e:
            print(f"Error guardando historial en disco: {e}")

    @staticmethod
    def resolve_trade_broker(trade: Dict[str, Any]) -> str:
        b = trade.get("broker")
        if b:
            return str(b).upper()
        cat = trade.get("category")
        if cat == "CRYPTO":
            return "BINANCE"
        elif cat in ("TRADFI_STOCK", "ETF"):
            return "ALPACA"
        return "SIMULATION"

    def record_trade(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Registra una operación completada y la guarda inmediatamente en el disco.
        """
        trade = {
            "id": trade_data.get("id", f"TR-{len(self.trades)+1:04d}"),
            "symbol": trade_data.get("symbol"),
            "name": trade_data.get("name", trade_data.get("symbol")),
            "icon": trade_data.get("icon", "📈"),
            "type": trade_data.get("type", "COMPRA / VENTA"),
            "quantity": trade_data.get("quantity", 1),
            "entry_price": round(trade_data.get("entry_price", 0.0), 2),
            "exit_price": round(trade_data.get("exit_price", 0.0), 2),
            "invested_amount": round(trade_data.get("invested_amount", 0.0), 2),
            "pnl": round(trade_data.get("pnl", 0.0), 2),
            "pnl_percent": round(trade_data.get("pnl_percent", 0.0), 2),
            "result": "GANANCIA" if trade_data.get("pnl", 0.0) > 0 else ("EMPATE" if trade_data.get("pnl", 0.0) == 0 else "PÉRDIDA CONTROLADA"),
            "reason": trade_data.get("reason", "Cierre por estrategia de IA"),
            "broker": trade_data.get("broker") or ("BINANCE" if trade_data.get("category") == "CRYPTO" else "ALPACA"),
            "category": trade_data.get("category", "CRYPTO"),
            "environment": trade_data.get("environment", "PAPER"),
            "opened_at": trade_data.get("opened_at", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "closed_at": trade_data.get("closed_at", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "duration": trade_data.get("duration", "2 min")
        }
        self.trades.insert(0, trade) # El más reciente primero
        # Mantener historial extenso sin truncar operaciones pasadas
        if len(self.trades) > 50000:
            self.trades.pop()
            
        self._save_to_disk()
        return trade

    def get_trades(self, limit: int = 50, broker: Optional[str] = None, environment: Optional[str] = None) -> List[Dict[str, Any]]:
        filtered = self.trades
        if broker and broker != "ALL":
            b_norm = broker.upper()
            filtered = [t for t in filtered if self.resolve_trade_broker(t) == b_norm]
        if environment:
            env_norm = environment.upper()
            filtered = [t for t in filtered if t.get("environment", "PAPER").upper() == env_norm]
        return filtered[:limit]

    def get_statistics(self, broker: Optional[str] = None, environment: Optional[str] = None) -> Dict[str, Any]:
        trades_pool = self.trades
        if broker and broker != "ALL":
            b_norm = broker.upper()
            trades_pool = [
                t for t in trades_pool
                if self.resolve_trade_broker(t) == b_norm
            ]
        if environment:
            env_norm = environment.upper()
            trades_pool = [
                t for t in trades_pool
                if t.get("environment", "PAPER").upper() == env_norm
            ]

        if not trades_pool:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "total_realized_pnl": 0.0,
                "best_trade": 0.0,
                "worst_trade": 0.0,
                "profit_factor": 1.0
            }

        total = len(trades_pool)
        wins = [t for t in trades_pool if t.get("pnl", 0.0) > 0]
        losses = [t for t in trades_pool if t.get("pnl", 0.0) < 0]
        ties = [t for t in trades_pool if t.get("pnl", 0.0) == 0]
        
        total_pnl = sum(t.get("pnl", 0.0) for t in trades_pool)
        gross_profit = sum(t.get("pnl", 0.0) for t in wins)
        gross_loss = abs(sum(t.get("pnl", 0.0) for t in losses))
        
        win_rate = round((len(wins) / total) * 100, 1) if total > 0 else 0.0
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)
        
        best_trade = max([t.get("pnl", 0.0) for t in trades_pool], default=0.0)
        worst_trade = min([t.get("pnl", 0.0) for t in trades_pool], default=0.0)

        return {
            "total_trades": total,
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "tie_trades": len(ties),
            "win_rate": win_rate,
            "total_realized_pnl": round(total_pnl, 2),
            "best_trade": round(best_trade, 2),
            "worst_trade": round(worst_trade, 2),
            "profit_factor": profit_factor
        }

    def get_daily_summary(self, broker: Optional[str] = None, environment: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Agrupa todas las operaciones históricas por día (YYYY-MM-DD) y calcula
        las métricas cuantitativas consolidadas para cada jornada.
        """
        from collections import Counter
        trades_pool = self.trades
        if broker and broker != "ALL":
            b_norm = broker.upper()
            trades_pool = [
                t for t in trades_pool
                if self.resolve_trade_broker(t) == b_norm
            ]
        if environment:
            env_norm = environment.upper()
            trades_pool = [
                t for t in trades_pool
                if t.get("environment", "PAPER").upper() == env_norm
            ]

        # Agrupar operaciones por día
        daily_groups: Dict[str, List[Dict[str, Any]]] = {}
        for t in trades_pool:
            date_str = (t.get("closed_at") or t.get("opened_at") or "")[:10]
            if not date_str:
                date_str = "SIN_FECHA"
            if date_str not in daily_groups:
                daily_groups[date_str] = []
            daily_groups[date_str].append(t)

        summaries = []
        for day, d_trades in sorted(daily_groups.items(), reverse=True):
            total_ops = len(d_trades)
            wins = [t for t in d_trades if t.get("pnl", 0.0) > 0]
            losses = [t for t in d_trades if t.get("pnl", 0.0) < 0]
            ties = [t for t in d_trades if t.get("pnl", 0.0) == 0]

            day_pnl = sum(t.get("pnl", 0.0) for t in d_trades)
            gross_win = sum(t.get("pnl", 0.0) for t in wins)
            gross_loss = abs(sum(t.get("pnl", 0.0) for t in losses))
            total_invested = sum(t.get("invested_amount", 0.0) for t in d_trades)

            win_rate = round((len(wins) / total_ops) * 100, 1) if total_ops > 0 else 0.0
            profit_factor = round(gross_win / gross_loss, 2) if gross_loss > 0 else (gross_win if gross_win > 0 else 1.0)
            avg_return = round(sum(t.get("pnl_percent", 0.0) for t in d_trades) / total_ops, 2) if total_ops > 0 else 0.0

            best_trade = max((t.get("pnl", 0.0) for t in d_trades), default=0.0)
            worst_trade = min((t.get("pnl", 0.0) for t in d_trades), default=0.0)

            # Símbolos más operados y más rentables
            sym_counts = Counter(t.get("symbol", "") for t in d_trades)
            most_traded_sym = sym_counts.most_common(1)[0][0] if sym_counts else "-"
            
            sym_pnls: Dict[str, float] = {}
            for t in d_trades:
                sym = t.get("symbol", "-")
                sym_pnls[sym] = sym_pnls.get(sym, 0.0) + t.get("pnl", 0.0)
            most_profitable_sym = max(sym_pnls.items(), key=lambda x: x[1])[0] if sym_pnls else "-"

            # Identificar brokers presentes en la jornada
            brokers_seen = sorted(list(set(self.resolve_trade_broker(t) for t in d_trades)))
            broker_label = brokers_seen[0] if len(brokers_seen) == 1 else "CONSOLIDADO"

            summaries.append({
                "date": day,
                "broker": broker_label,
                "brokers_list": brokers_seen,
                "total_trades": total_ops,
                "winning_trades": len(wins),
                "losing_trades": len(losses),
                "tie_trades": len(ties),
                "win_rate": win_rate,
                "realized_pnl": round(day_pnl, 2),
                "gross_profit": round(gross_win, 2),
                "gross_loss": round(gross_loss, 2),
                "profit_factor": profit_factor,
                "total_invested": round(total_invested, 2),
                "avg_return_percent": avg_return,
                "best_trade": round(best_trade, 2),
                "worst_trade": round(worst_trade, 2),
                "most_traded_symbol": most_traded_sym,
                "most_profitable_symbol": most_profitable_sym,
                "trades": d_trades
            })

        return summaries

    def export_trades_csv(self, broker: Optional[str] = None, mode: str = "complete", environment: Optional[str] = None) -> str:
        """
        Exporta el histórico estructurado con todas sus métricas en formato CSV (compatible Excel con BOM UTF-8).
        Modos soportados:
        - 'daily_summary': Solo tabla de métricas consolidadas por día.
        - 'detailed': Todas las operaciones individuales detalladas por día.
        - 'complete': Reporte exhaustivo con ambas secciones (Resumen diario + Desglose de operaciones).
        """
        import io
        output = io.StringIO()
        # Escribir UTF-8 BOM para compatibilidad inmediata con Microsoft Excel
        output.write('\ufeff')
        
        summaries = self.get_daily_summary(broker=broker, environment=environment)

        if mode in ["daily_summary", "complete"]:
            if mode == "complete":
                output.write("# =========================================================================================\n")
                output.write(f"# REPORTE HISTÓRICO CONSOLIDADO POR DÍA ({broker or 'TODOS LOS BROKERS'})\n")
                output.write(f"# Generado el: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                output.write("# =========================================================================================\n")

            daily_writer = csv.writer(output)
            daily_headers = [
                "Fecha_Dia",
                "Broker",
                "Total_Operaciones",
                "Operaciones_Ganadoras",
                "Operaciones_Perdedoras",
                "Operaciones_Empate",
                "Tasa_Acierto_Pct",
                "PnL_Neto_USD",
                "Ganancia_Bruta_USD",
                "Perdida_Bruta_USD",
                "Profit_Factor",
                "Volumen_Invertido_USD",
                "Rendimiento_Promedio_Trade_Pct",
                "Mejor_Operacion_USD",
                "Peor_Operacion_USD",
                "Activo_Mas_Operado",
                "Activo_Mas_Rentable"
            ]
            daily_writer.writerow(daily_headers)

            for d in summaries:
                daily_writer.writerow([
                    d["date"],
                    d["broker"],
                    d["total_trades"],
                    d["winning_trades"],
                    d["losing_trades"],
                    d["tie_trades"],
                    d["win_rate"],
                    d["realized_pnl"],
                    d["gross_profit"],
                    d["gross_loss"],
                    d["profit_factor"],
                    d["total_invested"],
                    d["avg_return_percent"],
                    d["best_trade"],
                    d["worst_trade"],
                    d["most_traded_symbol"],
                    d["most_profitable_symbol"]
                ])

        if mode == "complete":
            output.write("\n\n")
            output.write("# =========================================================================================\n")
            output.write("# DESGLOSE DETALLADO DE TRANSACCIONES OPERACIÓN POR OPERACIÓN CON TODAS SUS MÉTRICAS\n")
            output.write("# =========================================================================================\n")

        if mode in ["detailed", "complete"]:
            trades_writer = csv.writer(output)
            trade_headers = [
                "Fecha_Dia",
                "ID_Operacion",
                "Broker",
                "Simbolo",
                "Nombre_Activo",
                "Categoria",
                "Tipo_Orden",
                "Cantidad",
                "Precio_Entrada_USD",
                "Precio_Salida_USD",
                "Monto_Invertido_USD",
                "PnL_Realizado_USD",
                "Rendimiento_Pct",
                "Resultado",
                "Duracion",
                "Estrategia_Razón_Cierre",
                "Fecha_Apertura",
                "Fecha_Cierre"
            ]
            trades_writer.writerow(trade_headers)

            for d in summaries:
                for t in d["trades"]:
                    trades_writer.writerow([
                        d["date"],
                        t.get("id", ""),
                        self.resolve_trade_broker(t),
                        t.get("symbol", ""),
                        t.get("name", ""),
                        t.get("category", ""),
                        t.get("type", "COMPRA / VENTA"),
                        t.get("quantity", 0),
                        t.get("entry_price", 0.0),
                        t.get("exit_price", 0.0),
                        t.get("invested_amount", 0.0),
                        t.get("pnl", 0.0),
                        t.get("pnl_percent", 0.0),
                        t.get("result", ""),
                        t.get("duration", ""),
                        t.get("reason", ""),
                        t.get("opened_at", ""),
                        t.get("closed_at", "")
                    ])

        return output.getvalue()

    def clear(self):
        self.trades = []
        self._save_to_disk()
