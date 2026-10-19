# TitoBotTrader - Memoria Central de Configuración y Auditoría del Sistema
**Última Actualización:** 2026-10-19 16:55 COT
**Objetivo del Sistema:** Operación 100% enfocada y optimizada en **IQ Option**, eliminando intermediarios, brokers secundarios (Alpaca, Binance) y lógicas redundantes (como la Bóveda de ganancias).

---

## 1. Reglas Maestras de Operación
1. **Broker Único Exclusivo:** **IQ Option**. Todos los módulos de Alpaca y Binance quedan deshabilitados y eliminados del flujo operativo y de la interfaz visual para garantizar máximo rendimiento, cero latencia y cero confusión de saldo.
2. **Saldo Directo y Transparente:** Se elimina completamente el concepto de "Bóveda de Ganancias" (Profit Vault) y sus botones en la interfaz. El saldo operativo es directamente el saldo real de la cuenta de IQ Option (`real_amount` en COP).
3. **Persistencia y Memoria del Agente:** Toda configuración, lección técnica aprendida y estado del motor se persiste en este archivo y en la base de datos para que ningún reinicio o actualización borre el contexto.
4. **Pares OTC Son Exclusivamente Opciones Binarias:** En IQ Option los pares terminados en `-OTC` son contratos binarios digitales. Nunca se deben tratar como CFDs ni aplicarles Stop-Loss anticipado.

---

## 2. Modos Operativos de IQ Option
El usuario dispone de 3 modos seleccionables dinámicamente desde el dashboard o la API:

### Modo 1: `IQ_BINARY` (Opciones Binarias Turbo 60s)
* **Mecánica:** Contratos de expiración fija de 60 segundos ejecutados vía WebSocket oficial (`binary-options.open-option`).
* **Horarios:** Pares estándar durante sesión bancaria de lunes a viernes; pares OTC en horarios extendidos y 24/7.
* **Control de Salida:** Expiración por tiempo natural de 60 segundos. No admite cierres manuales ni Stop-Loss anticipado que mutile el contrato.
* **Gestión de Empate:** En caso de empate (`exit_price == entry_price`), el capital se reembolsa al 100% (`pnl = 0.0`).
* **Etiqueta en Bitácora:** En ganancias: `💰 ¡OPERACIÓN GANADA!`. En pérdidas: `🛑 CONTRATO NO CUMPLIDO`. En empates: `⚖️ EMPATE`.

### Modo 2: `IQ_CFD` (Forex Tradicional con Stop-Loss y Take-Profit)
* **Mecánica:** Operaciones de compra (`CALL/BUY`) y venta (`PUT/SELL`) sin tiempo de expiración fija sobre pares estándar bancarios.
* **Control de Salida:** La posición se mantiene abierta y es gestionada activamente por el motor cuantitativo segundo a segundo con:
  * **Take-Profit (TP):** Cierre automático al alcanzar el objetivo matemático de beneficio.
  * **Stop-Loss (SL):** Cierre defensivo si el precio toca el umbral de riesgo máximo (`🛡️ CIERRE DEFENSIVO STOP-LOSS`).
  * **Trailing Stop Dinámico:** Si la posición entra en ganancia, el Stop-Loss se desplaza protegiendo beneficios (Break-Even garantizado).

### Modo 3: `IQ_HYBRID` (Híbrido Inteligente Autónomo - Recomendado)
* **Pares OTC (`-OTC`):** Siempre se operan como **Opciones Binarias 60s**, ya que IQ Option no ofrece CFD para OTC.
* **Pares Estándar de Lunes a Viernes:**
  * Si el régimen detectado por la IA es de **Tendencia Fuerte** (`TRENDING_BULL` o `TRENDING_BEAR`): El bot entra en modo **Forex CFD** con Stop-Loss y Take-Profit para capturar movimientos largos sin el riesgo de expiración de 60 segundos.
  * Si el mercado está en **Consolidación / Rango Lateral** (`RANGING_SIDEWAYS`): El bot opera en **Opciones Binarias 60s** aprovechando rebotes en soportes y resistencias.
* **Fines de Semana (Bolsas Cerradas):**
  * Conmuta 100% de forma automática a **Binarias OTC 24/7** (`EURUSD-OTC`, `EURGBP-OTC`, `GBPUSD-OTC`, etc.) para seguir operando sin interrupción.

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
| **`Active %!s(MISSING) not found`** | IDs de activos OTC no existentes enviados a IQ Option. | Mapeo restringido exclusivamente a pares OTC oficiales y verificados. |
| **`the asset is not available at the moment`** | Pares Forex estándar intentando operarse fuera de su horario de mercado en IQ Option. | Enfriamiento preventivo inteligente de 10 minutos (`600s`) en activos cerrados y fallback inmediato a pares OTC activos. |
| **Pérdida en empates (Tie)** | Al cerrar con el mismo precio de entrada se declaraba -100%. | Soporte explícito de empate (`is_tie`): reembolso del 100% del capital invertido con `pnl = 0.0`. |
