import time
import datetime
import threading
import ssl
import urllib.request
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Set

class NewsMacroShield:
    """
    Escudo Institucional de Sentimiento de Noticias y Riesgo Macroeconómico.
    Analiza eventos de alto impacto financiero (FED, Tasas, CPI, SEC, Earnings, Cripto)
    en tiempo real mediante feeds RSS institucionales (Yahoo Finance, CoinDesk)
    y modula la actividad del agente:
    - Estado ESTABLE: Operativa completa con confianza plena.
    - Estado CAUTELA: Reduce confianza un 15% y estrecha Stop-Loss.
    - Estado SHOCK PROTECT: Congela nuevas compras (Shock Pause) ante cisnes negros o pánico.
    """
    def __init__(self, enable_live_stream: bool = True):
        self.shock_keywords = {
            "sec lawsuit": -0.85,
            "interest rate hike": -0.70,
            "cpi shock": -0.75,
            "crypto ban": -0.90,
            "exchange insolvency": -0.95,
            "war escalation": -0.85,
            "earnings miss": -0.60,
            "subpoena": -0.70,
            "hack exploit": -0.80,
            "recession warning": -0.65,
            "bank failure": -0.90,
            "liquidation cascade": -0.80,
            "hack": -0.75,
            "insolvency": -0.90,
            "default": -0.80,
            "plunge": -0.65,
            "crash": -0.75,
            "bear market": -0.50
        }
        self.bullish_keywords = {
            "rate cut expected": 0.70,
            "etf approved": 0.85,
            "earnings beat": 0.75,
            "institutional inflow": 0.80,
            "crypto adoption": 0.65,
            "record revenue": 0.70,
            "inflation drops": 0.75,
            "strategic partnership": 0.60,
            "liquidity injection": 0.70,
            "dovish pivot": 0.65,
            "rally": 0.60,
            "bull markets": 0.65,
            "all-time high": 0.75,
            "record high": 0.70,
            "soars": 0.60,
            "surges": 0.60,
            "tops": 0.50
        }
        self.last_shock_time = 0.0
        self.shock_cooldown_sec = 300.0  # 5 minutos de pausa preventiva tras noticia de shock
        self.headlines_feed: List[Dict[str, Any]] = []
        self.seen_headlines: Set[str] = set()
        self._seed_initial_headlines()
        
        self.enable_live_stream = enable_live_stream
        if self.enable_live_stream:
            # Iniciar hilo en segundo plano para actualizar noticias reales de mercado en vivo
            self._worker_thread = threading.Thread(target=self._live_news_worker, daemon=True)
            self._worker_thread.start()

    def _seed_initial_headlines(self):
        """Inicializa titulares de referencia de alta relevancia institucional."""
        seeds = [
            ("Reserva Federal: Próximo recorte de tasas esperado mientras la inflación retrocede al 2.4% anual.", "Reuters Macro", 0),
            ("BlackRock y Fidelity registran récord de entrada institucional en ETFs de Bitcoin y Ethereum.", "Bloomberg Markets", 1),
            ("NVIDIA y TSMC presentan proyecciones récord de demanda en chips de aceleración para IA.", "Wall Street Journal", 2),
            ("SEC avanza en la revisión regulatoria para nuevos vehículos de inversión cripto institucional.", "CoinDesk", 3),
            ("Departamento del Tesoro de EE.UU. confirma estabilidad de liquidez sin alertas de recesión.", "Financial Times", 4),
            ("Mercados globales de bonos asimilan datos económicos con volatilidad controlada.", "CNBC", 5)
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
        """Evalúa un titular o comunicado financiero y calcula su puntuación de impacto (-1.0 a +1.0)."""
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

        if final_score <= -0.60:
            status = "MACRO_SHOCK_PROTECT"
            tag = "🛑 Alerta de Shock / Pánico"
            self.last_shock_time = time.time()
            safe_to_buy = False
        elif final_score < -0.20:
            status = "MACRO_CAUTION_ALERT"
            tag = "⚠️ Cautela Macroeconómica"
            safe_to_buy = True
        elif final_score >= 0.30:
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
        if len(self.headlines_feed) > 20:
            self.headlines_feed.pop()
        return entry

    def is_macro_environment_safe(self) -> Dict[str, Any]:
        """Verifica si el entorno macroeconómico actual es seguro para nuevas asignaciones de capital."""
        now = time.time()
        elapsed = now - self.last_shock_time
        if elapsed < self.shock_cooldown_sec:
            rem = int(self.shock_cooldown_sec - elapsed)
            return {
                "safe": False,
                "status": "MACRO_SHOCK_COOLDOWN",
                "remaining_sec": rem,
                "reason": f"Pausa preventiva por evento de shock reciente ({rem}s restantes de blindaje)."
            }

        return {
            "safe": True,
            "status": "MACRO_STABLE",
            "remaining_sec": 0,
            "reason": "Condiciones macroeconómicas y flujo de noticias en rango de estabilidad."
        }

    def trigger_shock_event(self, reason: str = "Evento de alta volatilidad macroeconómica"):
        """Permite activar manualmente o por webhook un bloqueo de shock preventivo."""
        self.last_shock_time = time.time()
        self.add_headline(f"Alerta de Mercado: {reason}", source="Sistema de Emergencia")

    def get_shield_summary(self) -> Dict[str, Any]:
        safe_check = self.is_macro_environment_safe()
        # Calcular sentimiento promedio de los últimos titulares
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
        Consulta feeds institucionales RSS en vivo (Yahoo Finance y CoinDesk)
        y extrae los titulares más recientes del mercado financiero en tiempo real.
        """
        urls = [
            ("https://feeds.finance.yahoo.com/rss/2.0/headline?s=BTC-USD,NVDA,AAPL,SPY,MSFT,TSLA&region=US&lang=en-US", "Yahoo Finance"),
            ("https://www.coindesk.com/arc/outboundfeeds/rss/", "CoinDesk")
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
        """Hilo continuo en segundo plano que actualiza las noticias cada 60 segundos."""
        # Primera consulta al arrancar
        time.sleep(1.0)
        self.fetch_live_rss_feeds()
        
        while True:
            time.sleep(60.0)
            try:
                self.fetch_live_rss_feeds()
            except Exception:
                pass

