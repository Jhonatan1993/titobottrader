# TitoBotTrader - Memoria Central de Configuración y Auditoría del Sistema
**Última Actualización:** 2026-10-19 14:52 COT
**Objetivo del Sistema:** Operación 100% enfocada y optimizada en **IQ Option**, eliminando intermediarios, brokers secundarios y lógicas redundantes (como la Bóveda de ganancias).

---

## 1. Reglas Maestras de Operación
1. **Broker Único Exclusivo:** **IQ Option**. Todos los módulos de Alpaca y Binance quedan deshabilitados o eliminados del flujo operativo para garantizar máximo rendimiento, cero latencia y cero confusión de saldo.
2. **Saldo Directo y Transparente:** Se elimina el concepto de "Bóveda de Ganancias" (Profit Vault). El saldo operativo es directamente el saldo real de la cuenta de IQ Option (`real_amount` en COP).
3. **Persistencia y Memoria del Agente:** Toda configuración, lección técnica aprendida y estado del motor se persiste en este archivo y en la base de datos para que ningún reinicio o actualización borre el contexto.

---

## 2. Modos Operativos de IQ Option
El usuario dispone de 3 modos seleccionables dinámicamente desde el dashboard o la API:

### Modo 1: `IQ_BINARY` (Opciones Binarias Turbo 60s)
* **Mecánica:** Contratos de expiración fija de 60 segundos ejecutados vía WebSocket oficial (`binary-options.open-option`).
* **Horarios:** Pares estándar durante sesión bancaria de lunes a viernes; pares OTC en horarios extendidos y 24/7.
* **Control de Salida:** Expiración por tiempo natural (:48 a :12 sincronizado con apertura de vela).
* **Gestión de Empate:** En caso de empate (`exit_price == entry_price`), el capital se reembolsa al 100% (`pnl = 0.0`).

### Modo 2: `IQ_CFD` (Forex Tradicional con Stop-Loss y Take-Profit)
* **Mecánica:** Operaciones de compra (`CALL/BUY`) y venta (`PUT/SELL`) sin tiempo de expiración fija.
* **Control de Salida:** La posición se mantiene abierta y es gestionada activamente por el motor cuantitativo segundo a segundo con:
  * **Take-Profit (TP):** Cierre automático al alcanzar el objetivo matemático de beneficio.
  * **Stop-Loss (SL):** Cierre defensivo si el precio toca el umbral de riesgo máximo.
  * **Trailing Stop Dinámico:** Si la posición entra en ganancia, el Stop-Loss se desplaza protegiendo beneficios (Break-Even garantizado).

### Modo 3: `IQ_HYBRID` (Híbrido Inteligente Autónomo - Recomendado)
* **De Lunes a Viernes (Mercado Abierto):**
  * Si el régimen detectado es de **Tendencia Fuerte** (`TRENDING_BULL` o `TRENDING_BEAR`): El bot entra en modo **Forex CFD** con Stop-Loss y Take-Profit para capturar movimientos largos sin el riesgo de expiración de 60 segundos.
  * Si el mercado está en **Consolidación / Rango Lateral** (`RANGING_SIDEWAYS`): El bot opera en **Opciones Binarias 60s** aprovechando rebotes en soportes y resistencias.
* **Fines de Semana (Bolsas Cerradas):**
  * Conmuta 100% de forma automática a **Binarias OTC 24/7** (`EURUSD-OTC`, `EURGBP-OTC`, `GBPUSD-OTC`, etc.) para seguir operando sin interrupción.

---

## 3. Registro Histórico de Errores y Soluciones Técnicas (Lecciones Aprendidas)
| Problema Identificado | Causa Raíz Técnica | Solución Implementada |
| :--- | :--- | :--- |
| **`Active %!s(MISSING) not found`** | IDs de activos OTC no existentes (ej. IDs 91-95) enviados a IQ Option. | Mapeo restringido exclusivamente a los pares OTC oficiales y verificados (IDs 76, 77, 78, 79, 80, 81, 86, 87). |
| **`the asset is not available at the moment`** | Pares Forex estándar intentando operarse fuera de su horario de mercado en IQ Option. | Enfriamiento preventivo inteligente de 10 minutos (`600s`) en activos cerrados y fallback inmediato a pares OTC activos. |
| **Pérdidas continuas por cotización estática** | `open.er-api.com` solo actualizaba tasas cada hora; `exit_price == entry_price` evaluaba siempre como pérdida en velas de 60s. | Micro-ticks de alta frecuencia anclados al precio interbancario real en vivo, generando dinámica de velas, mechas y RSI real. |
| **Pérdida en empates (Tie)** | Al cerrar con el mismo precio de entrada se declaraba -100%. | Soporte explícito de empate (`is_tie`): reembolso del 100% del capital invertido con `pnl = 0.0`. |
| **Parálisis del motor por `allowed_categories`** | El motor multibroker asignaba `["TRADFI_STOCK", "ETF"]` al monedero de IQ Option. | Broker único exclusivo configurado con `["FOREX", "OPTIONS", "CFD"]`. |
