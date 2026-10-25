import os
import json
import logging
import numpy as np
import pandas as pd
import ta
from typing import Dict, Any, List, Optional

logger = logging.getLogger("SMCEngine")

class SMCEngine:
    """
    Motor Cuantitativo Institucional basado en Smart Money Concepts (SMC):
    - Fair Value Gaps (FVG / Imbalances) con desplazamiento de volumen (1.6x ATR).
    - Order Blocks (OB) con mitigación y propagación temporal (25 velas).
    - Barridos de Liquidez y Soportes/Resistencias Dinámicos (30 velas).
    - Patrones de Velas de Alta Probabilidad: Pinbars institucionales y Envolventes.
    - Confluencia de Tendencia y Momento: ADX, RSI y Bandas de Bollinger.
    - Soporte de Parámetros Dinámicos (optimal_params.json con recarga en caliente).
    """
    _optimal_cache: Dict[str, Any] = {}
    _last_mtime: float = 0.0

    @classmethod
    def get_data_dir(cls) -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        return data_dir

    @classmethod
    def load_optimal_params(cls, asset: str) -> dict:
        """Recarga automáticamente optimal_params.json si se actualizó en disco."""
        json_path = os.path.join(cls.get_data_dir(), "optimal_params.json")
        if os.path.exists(json_path):
            try:
                current_mtime = os.path.getmtime(json_path)
                if current_mtime != cls._last_mtime:
                    with open(json_path, "r", encoding="utf-8") as f:
                        cls._optimal_cache = json.load(f)
                    cls._last_mtime = current_mtime
            except Exception as e:
                logger.debug(f"Error leyendo optimal_params.json: {e}")

        default_cfg = {
            "min_adx": 20.0,
            "max_adx": 48.0,
            "rsi_oversold": 30.0,
            "rsi_overbought": 70.0,
            "pinbar_wick_ratio": 1.8,
            "ema_fast": 20,
            "ema_slow": 50,
            "ema_trend": 100
        }
        return cls._optimal_cache.get(asset, cls._optimal_cache.get("DEFAULT", default_cfg))

    @staticmethod
    def prepare_indicators(candles: List[Dict[str, Any]], params: Optional[dict] = None) -> pd.DataFrame:
        """
        Calcula indicadores vectorizados y huella institucional sobre velas japonesas.
        Soporta formato IQ Option ('max', 'min', 'open', 'close', 'volume').
        """
        if not candles or len(candles) < 35:
            return pd.DataFrame()

        df = pd.DataFrame(candles).copy()
        rename_map = {}
        if 'max' in df.columns:
            rename_map['max'] = 'high'
        if 'min' in df.columns:
            rename_map['min'] = 'low'
        if rename_map:
            df = df.rename(columns=rename_map)

        for col in ['open', 'high', 'low', 'close']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        close = df['close']
        high = df['high']
        low = df['low']

        cfg = params or {}
        ema_f = cfg.get("ema_fast", 20)
        ema_s = cfg.get("ema_slow", 50)
        ema_t = cfg.get("ema_trend", 100)

        # 1. Indicadores Técnicos Clásicos
        df['ema_fast'] = ta.trend.ema_indicator(close, window=ema_f)
        df['ema_slow'] = ta.trend.ema_indicator(close, window=ema_s)
        df['ema_trend'] = ta.trend.ema_indicator(close, window=min(ema_t, max(10, len(df) - 5)))
        df['rsi'] = ta.momentum.rsi(close, window=14)

        adx_ind = ta.trend.ADXIndicator(high, low, close, window=14)
        df['adx'] = adx_ind.adx()
        df['atr'] = ta.volatility.average_true_range(high, low, close, window=14)

        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        df['bb_lower'] = bb.bollinger_lband()
        df['bb_mid'] = bb.bollinger_mavg()
        df['bb_upper'] = bb.bollinger_hband()

        # 2. Soportes y Resistencias (Liquidez Institucional en ventana de 30 velas)
        win = min(30, max(5, len(df) - 2))
        df['resistance'] = high.rolling(window=win).max().shift(1)
        df['support'] = low.rolling(window=win).min().shift(1)

        # 3. Detección Vectorizada de Imbalances (FVG) y Order Blocks (SMC)
        body = (close - df['open']).abs()
        atr = df['atr'].fillna(body.mean())

        # Desplazamiento institucional: cuerpo de vela en t-1 supera 1.6x ATR
        displacement = body.shift(1) > (atr.shift(1) * 1.6)

        # Fair Value Gap Alcista (Espacio entre Low[t] y High[t-2])
        df['bull_fvg'] = (
            (low > high.shift(2)) &
            (close.shift(1) > df['open'].shift(1)) &
            displacement
        )
        # Fair Value Gap Bajista (Espacio entre High[t] y Low[t-2])
        df['bear_fvg'] = (
            (high < low.shift(2)) &
            (close.shift(1) < df['open'].shift(1)) &
            displacement
        )

        # Order Blocks (Zonas de origen del movimiento de desequilibrio)
        df['bull_ob_top'] = np.where(df['bull_fvg'], high.shift(2), np.nan)
        df['bull_ob_bottom'] = np.where(df['bull_fvg'], low.shift(2), np.nan)
        df['bear_ob_top'] = np.where(df['bear_fvg'], high.shift(2), np.nan)
        df['bear_ob_bottom'] = np.where(df['bear_fvg'], low.shift(2), np.nan)

        # Propagar Order Blocks activos hasta 25 velas mientras no sean mitigados
        df['bull_ob_top'] = df['bull_ob_top'].ffill(limit=25)
        df['bull_ob_bottom'] = df['bull_ob_bottom'].ffill(limit=25)
        df['bear_ob_top'] = df['bear_ob_top'].ffill(limit=25)
        df['bear_ob_bottom'] = df['bear_ob_bottom'].ffill(limit=25)

        return df

    @classmethod
    def analyze(cls, candles: List[Dict[str, Any]], asset: str = "DEFAULT") -> Dict[str, Any]:
        """
        Analiza las velas históricas y emite una recomendación institucional cuantitativa.
        Retorna decisión ('CALL', 'PUT', 'HOLD'), puntuación de confianza y motivo técnico.
        """
        params = cls.load_optimal_params(asset)
        df = cls.prepare_indicators(candles, params)

        if df.empty or len(df) < 30:
            return {
                "decision": "HOLD",
                "confidence": 0,
                "reason": "Velas insuficientes para cálculo de confluencia SMC.",
                "rsi": 50.0,
                "adx": 0.0,
                "strategy": "NONE"
            }

        min_adx = params.get("min_adx", 20.0)
        max_adx = params.get("max_adx", 48.0)
        rsi_os = params.get("rsi_oversold", 30.0)
        rsi_ob = params.get("rsi_overbought", 70.0)
        wick_ratio = params.get("pinbar_wick_ratio", 1.8)

        # Tomamos la última vela cerrada (iloc[-2]) y la penúltima (iloc[-3])
        c = df.iloc[-2]
        p = df.iloc[-3]

        body = abs(c['close'] - c['open'])
        candle_range = c['high'] - c['low']
        if candle_range <= 0.0:
            return {"decision": "HOLD", "confidence": 0, "reason": "Rango de vela nulo.", "rsi": 50.0, "adx": 0.0, "strategy": "NONE"}

        upper_wick = c['high'] - max(c['close'], c['open'])
        lower_wick = min(c['close'], c['open']) - c['low']

        # Anatomía de Velas
        bullish_engulfing = (
            p['close'] < p['open'] and
            c['close'] > c['open'] and
            c['close'] >= p['open'] and
            body > abs(p['close'] - p['open'])
        )
        bearish_engulfing = (
            p['close'] > p['open'] and
            c['close'] < c['open'] and
            c['close'] <= p['open'] and
            body > abs(p['close'] - p['open'])
        )

        bullish_pinbar = (lower_wick > body * wick_ratio) and (upper_wick < body * 0.5)
        bearish_pinbar = (upper_wick > body * wick_ratio) and (lower_wick < body * 0.5)

        rsi_val = float(c.get('rsi', 50.0))
        adx_val = float(c.get('adx', 0.0))
        adx_in_trend = (min_adx <= adx_val <= max_adx)

        # -------------------------------------------------------------
        # ESTRATEGIA 1: SMART MONEY CONCEPTS (Mitigación de Order Block)
        # -------------------------------------------------------------
        if pd.notna(c.get('bull_ob_top')) and pd.notna(c.get('bull_ob_bottom')):
            if (c['low'] <= c['bull_ob_top'] and
                c['close'] >= c['bull_ob_bottom'] and
                c['close'] > c['open'] and
                lower_wick > body * 0.8 and
                rsi_val < 62.0):
                return {
                    "decision": "CALL",
                    "confidence": 92,
                    "reason": f"SMC: Mitigación de Order Block Alcista + FVG (RSI {rsi_val:.1f}, ADX {adx_val:.1f})",
                    "rsi": rsi_val,
                    "adx": adx_val,
                    "strategy": "SMC_ORDER_BLOCK"
                }

        if pd.notna(c.get('bear_ob_top')) and pd.notna(c.get('bear_ob_bottom')):
            if (c['high'] >= c['bear_ob_bottom'] and
                c['close'] <= c['bear_ob_top'] and
                c['close'] < c['open'] and
                upper_wick > body * 0.8 and
                rsi_val > 38.0):
                return {
                    "decision": "PUT",
                    "confidence": 92,
                    "reason": f"SMC: Mitigación de Order Block Bajista + FVG (RSI {rsi_val:.1f}, ADX {adx_val:.1f})",
                    "rsi": rsi_val,
                    "adx": adx_val,
                    "strategy": "SMC_ORDER_BLOCK"
                }

        # -------------------------------------------------------------
        # ESTRATEGIA 2: REVERSIÓN EXTREMA (Bandas Bollinger + Pinbar + Soporte/Resistencia)
        # -------------------------------------------------------------
        if pd.notna(c.get('support')) and pd.notna(c.get('bb_lower')):
            if (c['low'] <= c['bb_lower'] and
                c['low'] <= c['support'] * 1.0005 and
                rsi_val < rsi_os and
                bullish_pinbar):
                return {
                    "decision": "CALL",
                    "confidence": 88,
                    "reason": f"Reversión Institucional: Pinbar en Soporte Dinámico y Bollinger Inferior (RSI {rsi_val:.1f})",
                    "rsi": rsi_val,
                    "adx": adx_val,
                    "strategy": "REVERSION_PINBAR"
                }

        if pd.notna(c.get('resistance')) and pd.notna(c.get('bb_upper')):
            if (c['high'] >= c['bb_upper'] and
                c['high'] >= c['resistance'] * 0.9995 and
                rsi_val > rsi_ob and
                bearish_pinbar):
                return {
                    "decision": "PUT",
                    "confidence": 88,
                    "reason": f"Reversión Institucional: Pinbar en Resistencia Dinámica y Bollinger Superior (RSI {rsi_val:.1f})",
                    "rsi": rsi_val,
                    "adx": adx_val,
                    "strategy": "REVERSION_PINBAR"
                }

        # -------------------------------------------------------------
        # ESTRATEGIA 3: CONTINUACIÓN DE TENDENCIA (EMA + Envolvente + ADX)
        # -------------------------------------------------------------
        if adx_in_trend:
            if (c['close'] > c.get('ema_trend', c['close']) and
                c.get('ema_fast', 0) > c.get('ema_slow', 0) and
                42.0 < rsi_val < 65.0 and
                bullish_engulfing):
                return {
                    "decision": "CALL",
                    "confidence": 84,
                    "reason": f"Continuación Tendencial: Envolvente Alcista con EMA y ADX Favorable ({adx_val:.1f})",
                    "rsi": rsi_val,
                    "adx": adx_val,
                    "strategy": "TREND_ENGULFING"
                }

            if (c['close'] < c.get('ema_trend', c['close']) and
                c.get('ema_fast', 0) < c.get('ema_slow', 0) and
                35.0 < rsi_val < 58.0 and
                bearish_engulfing):
                return {
                    "decision": "PUT",
                    "confidence": 84,
                    "reason": f"Continuación Tendencial: Envolvente Bajista con EMA y ADX Favorable ({adx_val:.1f})",
                    "rsi": rsi_val,
                    "adx": adx_val,
                    "strategy": "TREND_ENGULFING"
                }

        return {
            "decision": "HOLD",
            "confidence": max(50, int(adx_val)),
            "reason": f"Sin confluencia institucional en {asset} (RSI: {rsi_val:.1f}, ADX: {adx_val:.1f})",
            "rsi": rsi_val,
            "adx": adx_val,
            "strategy": "HOLD"
        }
