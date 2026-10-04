import time
from typing import Dict, List, Any, Optional

class FundingArbitrageScanner:
    """
    Escáner Cuantitativo de Arbitraje de Tasas de Financiación (Funding Rate Arbitrage).
    Estrategia Delta-Neutral institucional:
    - Mantiene una posición en Spot (Long) y una cobertura corta equivalente en Futuros Perpetuos (Short).
    - Captura los pagos periódicos de financiación (cada 8 horas) sin riesgo direccional de mercado.
    - Calcula el APR y APY proyectados y detecta oportunidades delta-neutrales de alto rendimiento.
    """
    def __init__(self):
        # Tasas base típicas de funding en 8 horas para criptomonedas líquidas
        self.benchmark_rates_8h = {
            "BTC": 0.00010,   # 0.010% por 8h (~10.95% APR anual)
            "ETH": 0.00012,   # 0.012% por 8h (~13.14% APR anual)
            "SOL": 0.00018,   # 0.018% por 8h (~19.71% APR anual)
            "BNB": 0.00009,   # 0.009% por 8h (~9.85% APR anual)
            "DOGE": 0.00022,  # 0.022% por 8h (~24.09% APR anual)
            "AVAX": 0.00015,  # 0.015% por 8h (~16.42% APR anual)
            "LINK": 0.00011,  # 0.011% por 8h (~12.04% APR anual)
            "NEAR": 0.00020,  # 0.020% por 8h (~21.90% APR anual)
        }
        self.maker_fee = 0.0002  # 0.02% comisión Maker Binance
        self.taker_fee = 0.0005  # 0.05% comisión Taker Binance

    def calculate_yield(self, symbol: str, rate_8h: Optional[float] = None) -> Dict[str, Any]:
        """Calcula el rendimiento anualizado APR y APY de una tasa de financiación."""
        clean_sym = symbol.upper().replace("USDT", "")
        effective_rate = rate_8h if rate_8h is not None else self.benchmark_rates_8h.get(clean_sym, 0.00010)

        # 3 pagos de funding al día, 365 días al año
        payments_per_year = 3 * 365
        apr_percent = round(effective_rate * payments_per_year * 100, 2)
        apy_percent = round(((1.0 + effective_rate) ** payments_per_year - 1.0) * 100, 2)

        # Costo de entrada/salida (2 operaciones Spot + 2 Futuros)
        round_trip_cost_pct = (self.maker_fee + self.taker_fee) * 2 * 100
        net_year_1_apr = round(max(0.0, apr_percent - round_trip_cost_pct), 2)

        if apr_percent >= 16.0:
            status = "🔥 EXCELENTE_DELTA_NEUTRAL"
            badge = "Alta Rentabilidad Pasiva"
            recommendation = "Desplegar estrategia Cash & Carry (Spot Long + Short Perpetuo)"
        elif apr_percent >= 9.0:
            status = "⭐ ATRACTIVO_ESTABLE"
            badge = "Rendimiento Fijo Superior"
            recommendation = "Apto para asignación de capital delta-neutral"
        elif apr_percent >= 0.0:
            status = "⚖️ NEUTRAL_BAJO"
            badge = "Tasa Estándar"
            recommendation = "Monitorear expansión de prima de futuros"
        else:
            status = "⚠️ INVERSO_BEAR"
            badge = "Financiación Negativa"
            recommendation = "No desplegar Cash & Carry (los cortos pagan a los largos)"

        return {
            "symbol": clean_sym,
            "rate_8h_pct": round(effective_rate * 100, 4),
            "apr_percent": apr_percent,
            "apy_compound_percent": apy_percent,
            "net_apr_after_fees": net_year_1_apr,
            "status": status,
            "badge": badge,
            "recommendation": recommendation,
            "risk_type": "Delta-Neutral (Cero Riesgo Direccional)"
        }

    def scan_all_crypto(self, crypto_symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Escanea todos los pares cripto monitoreados y los ordena por mayor APR neto."""
        symbols = crypto_symbols or list(self.benchmark_rates_8h.keys())
        results = [self.calculate_yield(sym) for sym in symbols]
        results.sort(key=lambda x: x["apr_percent"], reverse=True)
        return results

    def get_top_opportunity(self) -> Dict[str, Any]:
        """Retorna la mejor oportunidad de rendimiento pasivo en el mercado cripto."""
        scanned = self.scan_all_crypto()
        return scanned[0] if scanned else self.calculate_yield("BTC")
