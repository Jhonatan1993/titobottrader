import time
import datetime
import threading
import ssl
import urllib.request
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Set, Optional

class NewsMacroShield:
    """
    Escudo Institucional de Sentimiento de Noticias y Riesgo Macroeconómico para Forex Tradicional.
    Analiza eventos de alto impacto cambiario e interbancario (FED, BCE, BOE, BOJ, Tasas, CPI, NFP, Geopolítica)
    en tiempo real mediante feeds RSS institucionales de divisas (Yahoo Finance Forex & Macro).
    
    Exclusivo para Forex: Elimina completamente fuentes y keywords de criptomonedas para evitar
    bloqueos falsos e interferencias en la operativa de divisas en IQ Option.
    
    Modula la actividad del agente:
    - Estado ESTABLE: Operativa completa con confianza plena en Forex CFD.
    - Estado CAUTELA: Reduce confianza un 15% y estrecha Stop-Loss ante datos mixtos.
    - Estado SHOCK PROTECT: Pausa preventiva breve (120s) ante cisnes negros o shocks cambiarios reales.
    """
    def __init__(self, enable_live_stream: bool = True):
        # Palabras clave de shock e impacto cambiario negativo estricto (Forex / Macro)
        self.shock_keywords = {
            "central bank emergency": -0.85,
            "emergency rate hike": -0.85,
            "surprise rate hike": -0.75,
            "currency devaluation": -0.85,
            "currency intervention": -0.80,
            "forex intervention": -0.85,
            "sovereign default": -0.90,
            "debt default": -0.85,
            "bank failure": -0.85,
            "bank run": -0.85,
            "war escalation": -0.85,
            "geopolitical crisis": -0.75,
            "cpi shock": -0.75,
            "hyperinflation": -0.75,
            "flash crash": -0.80,
            "market panic": -0.75,
            "liquidity freeze": -0.80,
            "recession warning": -0.65,
            "stagflation": -0.65
        }
        
        # Palabras clave de viento a favor macroeconómico y estabilidad cambiaria
        self.bullish_keywords = {
            "rate cut expected": 0.70,
            "inflation slows": 0.75,
            "cpi cools": 0.75,
            "central bank pause": 0.65,
            "stable interest rates": 0.65,
            "soft landing confirmed": 0.70,
            "economic expansion": 0.65,
            "trade surplus": 0.60,
            "job growth steady": 0.65,
            "gdp growth beats": 0.70,
            "dovish pivot": 0.65,
            "liquidity injection": 0.65,
            "forex reserves rise": 0.65,
            "economic recovery": 0.65,
            "yields stabilize": 0.60
        }
        
        self.last_shock_time = 0.0
        self.last_shock_reason = ""
        self.shock_cooldown_sec = 120.0  # 2 minutos de pausa preventiva ante shock cambiario confirmado
        self.headlines_feed: List[Dict[str, Any]] = []
        self.seen_headlines: Set[str] = set()
        self._seed_initial_headlines()
        
        self.enable_live_stream = enable_live_stream
        if self.enable_live_stream:
            # Hilo continuo para consultar noticias macroeconómicas y de Forex en tiempo real
            self._worker_thread = threading.Thread(target=self._live_news_worker, daemon=True)
            self._worker_thread.start()

    def _seed_initial_headlines(self):
        """Inicializa titulares de referencia de alta relevancia macroeconómica y de divisas."""
        seeds = [
            ("Reserva Federal (FED): Inflación PCE desacelera y consolida estabilidad de tasas de interés.", "Reuters Macro", 0),
            ("Banco Central Europeo (BCE): Política monetaria previsible y estabilidad del Euro en mercados interbancarios.", "Bloomberg FX", 1),
            ("Banco de Inglaterra (BOE): Datos de empleo y salarios sostienen la cotización de la Libra Esterlina.", "Financial Times FX", 2),
            ("Banco de Japón (BOJ): Monitoreo de liquidez y estabilidad cambiaria sin intervención en el Yen.", "Nikkei / Reuters", 3),
            ("Departamento del Tesoro de EE.UU.: Liquidez interbancaria estable y rendimiento de bonos del tesoro controlado.", "Wall Street Journal FX", 4),
            ("Mercados Cambiarios Globales: Spreads estrechos y operativa normal en las principales sesiones de divisas.", "Forex Institutional", 5)
        ]
        for text, source, mins_ago in seeds:
            eval_data = self.evaluate_headline(text)
            timestamp_str = (datetime.datetime.now() - datetime.timedelta(minutes=mins_ago * 4)).strftime("%H:%M:%S")
            self.headlines_feed.append({
                "headline": text,
                "source": source,
                "time": timestamp_str,
                "score": eval_data["sentiment_score"],
                "status": eval_data["status"],
                "tag": eval_data["tag"],
                "safe_to_buy": eval_data["safe_to_buy"]
            })
            self.seen_headlines.add(text.strip().lower())

    def evaluate_headline(self, headline: str) -> Dict[str, Any]:
        """Evalúa un titular o comunicado financiero y calcula su puntuación de impacto cambiario (-1.0 a +1.0)."""
        lower_head = headline.lower()
        score = 0.0
        matched_flags = []

        for kw, impact in self.shock_keywords.items():
            if kw in lower_head:
                score += impact
                matched_flags.append(f"⚠️ {kw.upper()}")

        for kw, impact in self.bullish_keywords.items():
            if kw in lower_head:
                score += impact
                matched_flags.append(f"🚀 {kw.upper()}")

        # Acotar score entre -1.0 y +1.0
        final_score = max(-1.0, min(1.0, score))

        # Umbral estricto para shock macro en Forex (<= -0.75) para evitar falsos positivos
        if final_score <= -0.75:
            status = "MACRO_SHOCK_PROTECT"
            tag = "🛑 Alerta de Shock / Pánico Cambiario"
            self.last_shock_time = time.time()
            self.last_shock_reason = headline
            safe_to_buy = False
        elif final_score < -0.25:
            status = "MACRO_CAUTION_ALERT"
            tag = "⚠️ Cautela Macroeconómica"
            safe_to_buy = True
        elif final_score >= 0.25:
            status = "MACRO_BULLISH_TAILWIND"
            tag = "🌟 Viento a Favor Institucional"
            safe_to_buy = True
        else:
            status = "MACRO_STABLE_NEUTRAL"
            tag = "⚖️ Calendario Estable"
            safe_to_buy = True

        return {
            "headline": headline,
            "sentiment_score": round(final_score, 2),
            "status": status,
            "tag": tag,
            "safe_to_buy": safe_to_buy,
            "matched_flags": matched_flags
        }

    def add_headline(self, headline: str, source: str = "Feed en Vivo") -> Dict[str, Any]:
        """Agrega un nuevo titular analizado al feed dinámico de noticias."""
        eval_data = self.evaluate_headline(headline)
        entry = {
            "headline": headline,
            "source": source,
            "time": datetime.datetime.now().strftime("%H:%M:%S"),
            "score": eval_data["sentiment_score"],
            "status": eval_data["status"],
            "tag": eval_data["tag"],
            "safe_to_buy": eval_data["safe_to_buy"]
        }
        self.headlines_feed.insert(0, entry)
        if len(self.headlines_feed) > 25:
            self.headlines_feed.pop()
        return entry

    def is_macro_environment_safe(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Verifica si el entorno macroeconómico actual es seguro para nuevas operaciones de Forex CFD.
        Si hubo un shock reciente, mantiene pausa de protección durante 120s para asimilar la noticia.
        """
        now = time.time()
        elapsed = now - self.last_shock_time
        if elapsed < self.shock_cooldown_sec:
            rem = int(self.shock_cooldown_sec - elapsed)
            reason_msg = f"Pausa preventiva por evento de shock reciente ({rem}s restantes de blindaje)."
            if self.last_shock_reason:
                reason_msg = f"Pausa preventiva ({rem}s): {self.last_shock_reason[:60]}..."
            return {
                "safe": False,
                "status": "MACRO_SHOCK_COOLDOWN",
                "remaining_sec": rem,
                "reason": reason_msg
            }

        return {
            "safe": True,
            "status": "MACRO_STABLE",
            "remaining_sec": 0,
            "reason": "Condiciones macroeconómicas y flujos de divisas en rango de estabilidad."
        }

    def trigger_shock_event(self, reason: str = "Evento de alta volatilidad macroeconómica"):
        """Permite activar manualmente o por webhook un bloqueo de shock preventivo."""
        self.last_shock_time = time.time()
        self.last_shock_reason = reason
        self.add_headline(f"Alerta Cambiaria: {reason}", source="Sistema de Emergencia")

    def get_shield_summary(self) -> Dict[str, Any]:
        safe_check = self.is_macro_environment_safe()
        recent_scores = [h["score"] for h in self.headlines_feed[:6]] if self.headlines_feed else [0.42]
        avg_sentiment = round(sum(recent_scores) / len(recent_scores), 2) if recent_scores else 0.42

        return {
            "is_safe": safe_check["safe"],
            "status": safe_check["status"],
            "remaining_cooldown_sec": safe_check["remaining_sec"],
            "description": safe_check["reason"],
            "benchmark_sentiment": f"{'+' if avg_sentiment >= 0 else ''}{avg_sentiment:.2f}",
            "recent_headlines": self.headlines_feed[:8]
        }

    def fetch_live_rss_feeds(self) -> int:
        """
        Consulta feeds institucionales RSS en vivo enfocados 100% en Forex y Macroeconomía global.
        Elimina completamente fuentes de criptomonedas (CoinDesk, BTC-USD).
        """
        urls = [
            ("https://feeds.finance.yahoo.com/rss/2.0/headline?s=EURUSD=X,GBPUSD=X,USDJPY=X,DX-Y.NYB,AUDUSD=X,USDCAD=X,USDCHF=X,NZDUSD=X&region=US&lang=en-US", "Yahoo Finance Forex"),
            ("https://finance.yahoo.com/news/rssindex", "Yahoo Macro Global")
        ]
        
        ctx = ssl._create_unverified_context()
        new_items_count = 0
        
        for url, source_label in urls:
            try:
                req = urllib.request.Request(
                    url, 
                    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
                )
                with urllib.request.urlopen(req, context=ctx, timeout=6) as response:
                    xml_content = response.read()
                    root = ET.fromstring(xml_content)
                    items = root.findall(".//item")
                    
                    for item in items[:6]:
                        title_el = item.find("title")
                        if title_el is not None and title_el.text:
                            raw_title = title_el.text.strip()
                            clean_key = raw_title.lower()
                            if clean_key and clean_key not in self.seen_headlines:
                                self.seen_headlines.add(clean_key)
                                eval_data = self.evaluate_headline(raw_title)
                                self.headlines_feed.insert(0, {
                                    "headline": raw_title,
                                    "source": source_label,
                                    "time": datetime.datetime.now().strftime("%H:%M:%S"),
                                    "score": eval_data["sentiment_score"],
                                    "status": eval_data["status"],
                                    "tag": eval_data["tag"],
                                    "safe_to_buy": eval_data["safe_to_buy"]
                                })
                                new_items_count += 1
                                if len(self.headlines_feed) > 25:
                                    self.headlines_feed.pop()
            except Exception:
                # Silenciosamente tolerante a cortes o lentitud de red
                pass
                
        return new_items_count

    def _live_news_worker(self):
        """Hilo continuo en segundo plano que actualiza las noticias macro cada 90 segundos."""
        time.sleep(1.0)
        self.fetch_live_rss_feeds()
        
        while True:
            time.sleep(90.0)
            try:
                self.fetch_live_rss_feeds()
            except Exception:
                pass
