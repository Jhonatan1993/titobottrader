# TitoBotTrader - Memoria Central de Configuración y Auditoría del Sistema
**Última Actualización:** 2026-10-20 13:30 COT
**Objetivo del Sistema:** Operación 100% enfocada y optimizada en **Forex Tradicional (CFD) en IQ Option**, eliminando intermediarios, brokers secundarios (Alpaca, Binance), y erradicando completamente las opciones binarias y lógicas redundantes (como la Bóveda de ganancias).

---

## 1. Reglas Maestras de Operación
1. **Broker Único Exclusivo:** **IQ Option**. Todos los módulos de Alpaca y Binance quedan deshabilitados y eliminados del flujo operativo y de la interfaz visual para garantizar máximo rendimiento, cero latencia y cero confusión de saldo.
2. **Modelo Único Exclusivo: Forex Tradicional (CFD):**
   - **PROHIBICIÓN TOTAL DE OPCIONES BINARIAS:** Se eliminan de raíz las opciones binarias (`IQ_BINARY`, `IQ_HYBRID`, expiraciones de 60 segundos, payouts binarios y compuertas de tiempo de vela). El análisis de pérdidas reales del 19 de octubre demostró que la asimetría de binarias destruye el capital.
   - Toda operación en IQ Option se ejecuta como **Forex CFD** con Stop-Loss matemático, Take-Profit garantizado (R:R mínimo 1:2.0), Break-Even automático a +1R y Trailing Stop dinámico a partir de +1.5R.
3. **Saldo Directo y Transparente:** Se elimina completamente el concepto de "Bóveda de Ganancias" (Profit Vault) y sus botones en la interfaz. El saldo operativo es directamente el saldo real de la cuenta de IQ Option (`real_amount` en COP).
4. **Política Estricta de Despliegue a VPS:**
   - **NUNCA** realizar despliegues automáticos, `git push` o reinicios en el VPS sin antes explicar detallada y concisamente los cambios al usuario y obtener su aprobación explícita o permitir que él mismo ejecute los comandos en la consola del servidor.
5. **Persistencia y Memoria del Agente:** Toda configuración, directiva del usuario, lección técnica y bitácora de chat se persiste en `data/PROJECT_CONVERSATION_LOG.md`, en este archivo y en la base de datos para que ningún reinicio o corte de sesión borre el contexto.

---

## 2. Mecánica Operativa: Forex CFD en IQ Option
* **Mecánica:** Operaciones de compra (`CALL/BUY`) y venta (`PUT/SELL`) basadas en confluencia técnica (EMA 20/50, RSI, soportes y resistencias, régimen de mercado) sin expiración forzada de 60s.
* **Relación Riesgo / Beneficio (R:R):** Mínimo 1:2.0 o 1:2.5 a favor. Solo se requiere ~35% de Win Rate para ser rentable.
* **Control de Salida Dinámico:**
  * **Take-Profit (TP):** Cierre automático garantizado al alcanzar el objetivo de beneficio matemático.
  * **Stop-Loss (SL):** Cierre defensivo estricto para preservar capital si el precio se mueve en contra.
  * **Break-Even Automático (+1R):** Al avanzar el precio a +1R de ganancia favorable, el Stop-Loss se mueve de inmediato al precio de entrada (`entry_price`), blindando la operación a CERO RIESGO.
  * **Trailing Stop (+1.5R):** Acompaña la tendencia asegurando al menos +0.5R de beneficio acumulado ante cualquier retroceso.
* **Filtro de Horarios de Mercado:** El bot opera pares Forex disponibles durante sesiones activas de mercado. Si un activo se encuentra cerrado, se aplica enfriamiento inteligente para no saturar la API.

---

## 3. Registro Histórico de Errores y Soluciones Técnicas (Lecciones Aprendidas)
| Problema Identificado | Causa Raíz Técnica | Solución Implementada |
| :--- | :--- | :--- |
| **Presencia visual de Alpaca y Binance en el Dock** | El endpoint `get_state()` devolvía todas las carteras residuales en `sys.brokers`, y el bucle JS renderizaba los botones de Alpaca y Binance. | Filtro estricto en backend y frontend para exponer y renderizar EXCLUSIVAMENTE la cápsula de IQ Option. |
| **Botón residual "🔒 A Bóveda" en Cartera** | Línea 2159 en `index.html` conservaba el botón HTML de cosecha de bóveda. | Eliminado el botón por completo. El PnL se refleja de forma directa y transparente en el capital. |
| **Bloqueo del 100% de órdenes de Venta/Baja (PUT)** | En `intelligent_agent.py`, el retorno de `evaluate_asset` asignaba `confidence: adjusted_conf` (la métrica alcista) aún cuando la decisión era `SELL` (bajista), enviando confianzas de 30-40% y descartando todos los PUTs. | Corrección: ahora retorna `confidence: adjusted_conf_bear` cuando `decision == "SELL"`, permitiendo abrir PUTs con confianza >= 82%. |
| **Parálisis tras 1-2 operaciones** | Compuerta de tiempo rígida (`sec >= 48 or sec <= 12`) descartaba el 60% de los ticks; sumado al bloqueo de PUTs y cooldowns acumulados, el motor no encontraba candidatos. | Compuerta de tiempo ampliada (`sec >= 35 or sec <= 25`), habilitación de operaciones PUT y depuración de cooldowns individuales. |
| **Confusión visual de "Cierre Defensivo" en Binarias** | Se usaba el texto `🛡️ CIERRE DEFENSIVO` para cualquier pérdida, haciendo parecer que se ejecutó un Stop-Loss anticipado en una binaria. | Diferenciación de mensajes: `🛑 CONTRATO NO CUMPLIDO` para binarias expiradas en pérdida, reservando `🛡️ CIERRE DEFENSIVO STOP-LOSS` para CFDs. |
| **Parálisis tras 1 sola pérdida (Bloqueo 5% `RiskManager`)** | `RiskManager.can_open_trade()` tenía un límite estático de pérdida diaria de 5% sobre el capital (`1,197 COP` para `23,949 COP`). Como 1 contrato mínimo de IQ Option cuesta `2,000 COP` (~8.3%), la primera pérdida del día superaba el 5% y bloqueaba silenciosamente todas las operaciones subsiguientes hasta reiniciar el servidor. | Se adaptó `RiskManager.can_open_trade()` para IQ Option: respeta el límite explícito configurado por el usuario en la interfaz (`max_loss_amount`), sin aplicar el 5% rígido de TradFi en cuentas micro de COP, y se agregó limpieza de pérdidas diarias al reiniciar cooldowns. |
| **Apertura de 3-4 operaciones simultáneas (Drenaje de saldo)** | `max_positions` estaba configurado en 3 (y hasta 5 en riesgo). En cada tick el motor abría órdenes simultáneas en activos correlacionados (`GBPUSD`, `EURJPY`, `GBPJPY`), arriesgando hasta 8,000 COP a la vez en cuentas micro. | Restricción estricta de `max_positions = 1` en IQ Option: solo se permite una única operación abierta a la vez; hasta que no finalice y liquide, el bot no abre la siguiente. |
| **Operación a ciegas por generador estocástico artificial** | `market_feed.py` no obtenía velas reales de Forex/OTC desde IQ Option, cayendo a un generador artificial de ruido gaussiano (`random.gauss`), evaluando indicadores técnicos sobre datos simulados desconectados de las cotizaciones reales de IQ Option. | Se implementó `IQOptionAdapter.get_candles()` vía WebSocket oficial (`get-candles` 60s) conectado directamente a `market_feed.py`, asegurando que el análisis de EMA, RSI y soportes/resistencias se realice sobre velas reales de IQ Option. |
| **`Active %!s(MISSING) not found`** | IDs de activos OTC no existentes enviados a IQ Option. | Mapeo restringido exclusivamente a pares OTC oficiales y verificados. |
| **`the asset is not available at the moment`** | Pares Forex estándar intentando operarse fuera de su horario de mercado en IQ Option. | Enfriamiento preventivo inteligente de 10 minutos (`600s`) en activos cerrados y fallback inmediato a pares OTC activos. |
| **Pérdida en empates (Tie)** | Al cerrar con el mismo precio de entrada se declaraba -100%. | Soporte explícito de empate (`is_tie`): reembolso del 100% del capital invertido con `pnl = 0.0`. |
| **Sobrescritura de `operating_mode` al cambiar de broker activo** | `set_active_broker("IQOPTION")` forzaba `operating_mode = "IQOPTION_FOREX"`, sobrescribiendo el modo configurado (`IQ_CFD`, `IQ_BINARY`, `IQ_HYBRID`) y alterando la lógica de evaluación en pruebas y ejecución. | Se preserva el modo operativo configurado en `set_active_broker()` y se aisló la suite `test_forex_cfd_strict_guarantees.py` garantizando el contexto exclusivo `IQ_CFD`. |
| **Disparo encubierto de Opciones Binarias en Modo Real (Causa Raíz de Pérdidas)** | En `execution/iqoption_adapter.py`, el método `_execute_real_ws_order` enviaba `binary-options.open-option` con expiración de 60 segundos y `close_option` enviaba `binary-options.sell-option`. Aunque el motor gestionaba posiciones como CFD, a IQ Option se le enviaban órdenes reales de binarias turbo de 60s, liquidando capital por ruido de corto plazo. | Migración integral de la capa WebSocket a Forex CFD oficial: apertura mediante `place-order-temp` (v4.0, `instrument_type="forex"`, leverage x25, Stop-Loss y Take-Profit automáticos) y cierre mediante `close-position` (v1.0). Cero invocaciones a `binary-options` en todo el adaptador. |
| **Bloqueo de Forex por titulares de Criptomonedas** | `news_sentiment_shield.py` consultaba feeds de CoinDesk y BTC-USD con keywords de cripto (`crypto ban`, `hack exploit`). Shocks en criptomonedas congelaban la operativa de Forex CFD en IQ Option por 5 minutos innecesariamente. | Saneamiento total: feeds reorientados 100% a Forex y Macroeconomía global (Yahoo Finance Forex: DXY, EURUSD, GBPUSD, USDJPY, Bancos Centrales FED/BCE/BOE/BOJ). Cero criptomonedas y cooldown ajustado a 120s. |


