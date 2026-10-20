# Bitácora Central de Decisiones y Conversaciones (PROJECT_CONVERSATION_LOG.md)

Este documento registra de forma cronológica, inmutable y persistente todas las directivas del usuario, análisis críticos y acuerdos de arquitectura del proyecto **TitoBotTrader**. Si la sesión se reinicia o se pierde la memoria de contexto, este archivo debe consultarse primero para mantener el rumbo acordado.

---

## 📌 Directivas Maestras del Usuario (Inviolables)

1. **PROHIBICIÓN TOTAL DE OPCIONES BINARIAS:**
   - Se elimina de raíz cualquier lógica, modo, compuerta o prueba de Opciones Binarias (`IQ_BINARY`, `IQ_HYBRID`, expiraciones de 60s, compuerta de segundo :00/:58, payouts binarios).
   - El análisis del histórico de operaciones del 19 de octubre de 2026 demostró que la asimetría matemática de las binarias (arriesgar el 100% para ganar 80-88% con expiraciones fijas de 60 segundos) causó la pérdida de capital real, anula el análisis técnico y carece de gestión de riesgo (no permite Stop-Loss dinámico ni dejar correr ganancias).
   - El bot debe ser **100% FOREX TRADICIONAL (CFD)** en **IQ Option**, con:
     - Stop-Loss estricto y matemático.
     - Take-Profit objetivo (mínimo 1:2 de Riesgo/Beneficio).
     - Break-Even automático a +1R (proteger capital a cero riesgo).
     - Trailing Stop dinámico a partir de +1.5R.
2. **POLÍTICA DE DESPLIEGUE A VPS (ESTRICTA):**
   - **NUNCA** subir cambios, ejecutar `git push`, reiniciar servicios ni realizar despliegues automáticos al VPS sin previa explicación detallada y concisa.
   - El usuario debe dar su aprobación explícita primero, o en su defecto, se le entregarán los comandos exactos para que él mismo los ejecute en la consola del VPS.
3. **BROKER ÚNICO:**
   - Exclusivamente **IQ Option**. Binance y Alpaca están completamente deshabilitados.
4. **CERO CONFUSIÓN DE SALDO:**
   - Saldo real directo de la cuenta IQ Option. Sin bóvedas ficticias ni divisiones confusas.

---

## 📅 Registro Cronológico de Eventos y Sesiones

### Sesión 19 de Octubre 2026: Auditoría de Pérdidas y Cambio de Paradigma
* **Diagnóstico:** Se analizó el historial de operaciones de la cuenta real. La operativa con opciones binarias turbo de 60s generó pérdidas acumuladas por asimetría de retorno y ruido estocástico de corto plazo.
* **Decisión Estratégica:** Abandonar completamente las opciones binarias y migrar 100% el motor a Forex Tradicional (CFD) con gestión de riesgo matemática (R:R 1:2.5, Break-Even, Trailing Stop).

### Sesión 20 de Octubre 2026: Purgado Definitivo de Binarias y Protección de Despliegue
* **Problema:** En la sesión anterior se habían dejado tests y selectores residuales de binarias que provocaron confusiones y fallos en suites heredadas.
* **Instrucción del Usuario:**
  1. Registrar esta bitácora persistente de conversaciones para no perder nunca el rumbo.
  2. Realizar un barrido completo en todo el código para extirpar cualquier vestigio de binarias (en lógica, modos, dashboard y pruebas).
  3. Reemplazar o adaptar las suites de prueba exclusivamente a Forex CFD.
  4. Bloquear cualquier despliegue a VPS sin previa autorización y explicación detallada.
* **Acciones Ejecutadas:**
  - Barrido completo en `execution/trading_engine.py`: eliminado `IQ_BINARY`, `IQ_HYBRID`, compuertas de tiempo de vela (:00/:58), filtro de payout binario (<80%) y expiraciones fijas de 60s. Todas las operaciones se abren y gestionan 100% como Forex CFD (`duration_sec=0`, con SL, TP, Break-Even dinámico y Trailing Stop).
  - Barrido en `market_data/market_feed.py`: modo predeterminado fijado a `IQ_CFD`.
  - Limpieza visual en `dashboard/templates/index.html`: eliminados selectores y badges de binarias/híbrido; el dashboard expone exclusivamente el modo Forex Tradicional CFD con SL/TP.
  - Purgado de suites de prueba: eliminadas `test_binary_options_strict_guarantees.py`, `test_iqoption_three_modes.py` y `test_broker_financial_symmetry.py`.
  - Implementación de `tests/test_forex_cfd_strict_guarantees.py`: 7 garantías estrictas de Forex CFD (ejecución CALL/PUT, Stop-Loss dinámico, Take-Profit objetivo, Break-Even a +1R, Trailing Stop a +1.5R y liquidación sin bóvedas).
  - **Hallazgo Crítico (Causa Raíz de Pérdidas Reales Resuelta):** Se detectó que en `execution/iqoption_adapter.py`, el método `_execute_real_ws_order` aún enviaba payloads de opciones binarias (`binary-options.open-option` con expiración fija de 60 segundos) y `close_option` enviaba `binary-options.sell-option`. En vivo, el broker abría binarias de 60 segundos provocando pérdidas inmediatas de capital.
  - **Corrección Integral en `iqoption_adapter.py`:** Se migró la orden WebSocket a la API oficial de Forex CFD (`place-order-temp`, versión 4.0, `instrument_type="forex"`, con apalancamiento x25, `stop_lose_kind="percent"` y `take_profit_kind="percent"`). Se implementó `close_position` oficial (`close-position`, versión 1.0).
  - **Pruebas de Payload:** Se incorporaron pruebas unitarias estrictas en `tests/test_iqoption_real_execution.py` que inspeccionan los mensajes WebSocket transmitidos, confirmando que NUNCA contienen `binary-options.open-option`, ni `option_type_id`, ni expiración de 60s.
  - **Verificación Global:** Se ejecutaron todas las suites con 100% de éxito.
  - **Estado de Git y VPS:** Cambios aprobados por el usuario. Commits subidos exitosamente a GitHub (rama `main`, commit `323a09a`). Listo para sincronización en el VPS.

