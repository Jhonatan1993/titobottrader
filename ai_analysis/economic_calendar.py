import os
import time
import logging
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Tuple, List, Dict, Any, Optional

logger = logging.getLogger("EconomicCalendar")

class EconomicCalendarFilter:
    """
    Filtro de Calendario Económico Institucional (ForexFactory XML).
    Descarga los eventos macroeconómicos de la semana y bloquea operaciones en activos
    relacionados a noticias de ALTO IMPACTO (High Impact) dentro de una ventana de ±15 minutos.
    
    Características:
    - Caché local en disco (data/ff_calendar.xml) con actualización cada 6 horas.
    - Soporte automático para pares OTC (los activos OTC operan 24/7 y no dependen de noticias macro).
    - Mapeo inteligente de divisas base y cotizada (EUR, USD, GBP, JPY, AUD, CAD, CHF, NZD).
    """
    def __init__(self, window_minutes: int = 15):
        self.feed_url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
        self.window = timedelta(minutes=window_minutes)
        self.high_impact_events: List[Dict[str, Any]] = []
        self.last_fetch: Optional[datetime] = None
        
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.cache_dir = os.path.join(base_dir, "data")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache_file = os.path.join(self.cache_dir, "ff_calendar.xml")

    def update_calendar(self, force: bool = False) -> None:
        """Descarga el calendario económico y actualiza el caché en memoria."""
        now = datetime.now(timezone.utc)
        if not force and self.last_fetch and (now - self.last_fetch).total_seconds() < 21600:
            return

        # Intentar cargar desde caché local si es reciente (< 6 horas)
        if not force and os.path.exists(self.cache_file):
            try:
                mtime = os.path.getmtime(self.cache_file)
                if (time.time() - mtime) < 21600:
                    with open(self.cache_file, "rb") as f:
                        self._parse_xml(f.read())
                    self.last_fetch = datetime.fromtimestamp(mtime, tz=timezone.utc)
                    return
            except Exception as e:
                logger.debug(f"Error cargando caché XML local: {e}")

        # Descarga desde el feed remoto
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            response = requests.get(self.feed_url, headers=headers, timeout=12)
            if response.status_code == 200 and response.content:
                with open(self.cache_file, "wb") as f:
                    f.write(response.content)
                self._parse_xml(response.content)
                self.last_fetch = now
                logger.info(f"Calendario económico actualizado: {len(self.high_impact_events)} eventos de Alto Impacto cargados.")
        except Exception as e:
            logger.warning(f"No se pudo descargar calendario económico remoto: {e}")
            if os.path.exists(self.cache_file):
                try:
                    with open(self.cache_file, "rb") as f:
                        self._parse_xml(f.read())
                except Exception:
                    pass

    def _parse_xml(self, xml_bytes: bytes) -> None:
        """Parsea el contenido XML e indexa eventos de Alto Impacto."""
        try:
            root = ET.fromstring(xml_bytes)
            events = []
            for event in root.findall('event'):
                impact_el = event.find('impact')
                impact = impact_el.text if impact_el is not None else ""
                if impact and impact.strip().lower() == 'high':
                    country_el = event.find('country')
                    date_el = event.find('date')
                    time_el = event.find('time')
                    title_el = event.find('title')

                    country = country_el.text.strip().upper() if country_el is not None and country_el.text else ""
                    date_str = date_el.text.strip() if date_el is not None and date_el.text else ""
                    time_str = time_el.text.strip() if time_el is not None and time_el.text else ""
                    title = title_el.text.strip() if title_el is not None and title_el.text else ""

                    if time_str and ('am' in time_str.lower() or 'pm' in time_str.lower()):
                        try:
                            dt_str = f"{date_str} {time_str}"
                            event_dt = datetime.strptime(dt_str, "%m-%d-%Y %I:%M%p").replace(tzinfo=timezone.utc)
                            events.append({
                                "currency": country,
                                "time": event_dt,
                                "title": title
                            })
                        except Exception:
                            continue
            self.high_impact_events = events
        except Exception as e:
            logger.error(f"Error procesando XML de ForexFactory: {e}")

    def is_safe_to_trade(self, asset: str) -> Tuple[bool, str]:
        """
        Determina si un activo puede ser operado con seguridad macroeconómica.
        Retorna (is_safe: bool, motivo: str).
        """
        asset_clean = str(asset).upper()
        # Mercados OTC no sufren el impacto de noticias del mercado interbancario
        if "-OTC" in asset_clean or "OTC" in asset_clean:
            return True, "Activo OTC (Operativa algorítmica continua sin interferencia macro)."

        self.update_calendar()
        if not self.high_impact_events:
            return True, "Calendario económico neutral (Sin noticias de alto impacto activas)."

        now = datetime.now(timezone.utc)
        # Extraer monedas base y cotizada (ej: EURUSD -> EUR y USD)
        clean_code = asset_clean.replace("/", "").replace("_", "").replace("-", "")
        base_curr = clean_code[:3]
        quote_curr = clean_code[3:6] if len(clean_code) >= 6 else ""

        for ev in self.high_impact_events:
            ev_curr = ev.get("currency", "")
            if ev_curr in (base_curr, quote_curr):
                time_diff = abs(now - ev["time"])
                if time_diff <= self.window:
                    rem_min = int((self.window - time_diff).total_seconds() / 60)
                    return False, f"⚠️ BLOQUEO MACRO ({ev_curr}): Noticia de Alto Impacto '{ev['title']}' activa en ventana de ±15m (Riesgo remanente: ~{rem_min} min)."

        return True, "Sin noticias institucionales de alto impacto cercanas."
