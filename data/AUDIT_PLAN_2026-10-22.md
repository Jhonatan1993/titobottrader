# Auditoría Integral y Plan Obligatorio de Mejora — 2026-10-22

> **Corrección de alcance — 2026-10-28:** Por decisión posterior del usuario se conservan dos modalidades seleccionables y aisladas: `BINARY_OPTIONS` y `FOREX_CFD` (margen). Las propuestas de este documento que ordenaban eliminar binarias o quitar el selector quedan reemplazadas. La modalidad binaria sigue disponible en PAPER; `LIVE_REAL` binario permanece bloqueado hasta reconciliar liquidaciones con resultados oficiales del broker. La habilitación de CFD real también requiere validar tamaño de contrato y margen frente al importe solicitado.

## Alcance y límite de responsabilidad

Auditoría de arquitectura, ejecución IQ Option, Forex CFD/margen, gestión de riesgo, datos de mercado, estrategia, IA, backtesting, trazabilidad, dashboard, seguridad, despliegue, registros y pruebas.

**No es posible garantizar ganancias, porcentaje de acierto, ausencia de pérdidas, Take-Profit garantizado ni rendimiento futuro.** En CFDs/margen existen pérdidas, spread, deslizamiento, gaps, liquidación, rechazos y fallos de conectividad. El objetivo obligatorio es limitar y hacer verificable el riesgo, nunca prometer rentabilidad.

## Veredicto actual

# NO APTO PARA OPERACIÓN REAL AUTÓNOMA

La suite local actual termina con `100 passed`, pero eso no certifica seguridad operativa: conserva rutas binarias, datos simulados que pueden alimentar decisiones, discrepancias de PnL/apalancamiento, cierre local previo a confirmación del broker y exposición de secretos.

**Regla inmediata:** mantener el sistema en `PAPER`. `LIVE_REAL` debe permanecer bloqueado hasta cumplir íntegramente los controles P0 y los criterios de aceptación de este documento.

---

## Reglas vinculantes sin excepción

1. **Productos permitidos:** únicamente IQ Option, con selector entre Binarias y Forex CFD/margen.
   - Las lógicas, riesgos y resultados deben permanecer aislados por modalidad. Binarias pueden operar en PAPER; binarias LIVE_REAL quedan bloqueadas sin liquidación oficial conciliable.
   - El allowlist de CFD excluye OTC. OTC solo puede pertenecer a una modalidad binaria de práctica y nunca debe convertirse automáticamente en CFD.
2. **Broker permitido en producción:** IQ Option únicamente.
   - Binance, Alpaca, bóvedas, arbitraje crypto, alta de brokers y modo multibroker no se inicializan ni se exponen en la ruta productiva.
3. **Diseño fail-closed:** si el símbolo no está permitido, el feed es sintético/obsoleto, el broker no confirma, faltan SL/TP, hay una excepción o la reconciliación falla, la orden debe ser rechazada.
4. **Fuente de verdad:** IQ Option es la única autoridad para saldo, posición, fill, precio de entrada, margen, SL, TP y cierre. El estado local solo cambia con evidencia correlacionada (`request_id`, `order_id`, `position_id`).
5. **Datos en real:** prohibido abrir operaciones con fuente `SIMULATION`, ruido aleatorio, velas sintéticas, velas abiertas o precios externos no ejecutables en IQ Option. Exigir bid/ask, UTC, antigüedad máxima y velas cerradas del instrumento CFD.
6. **Riesgo por delante de señal:** una señal, IA, RSI, EMA o “confianza” nunca puede eludir el motor de riesgo.
7. **Cambios/despliegues:** sin `git push`, despliegue, reinicio, conexión o prueba real sin explicación, aprobación explícita del usuario, pruebas aprobadas, backup/rollback y registro.
8. **Memoria obligatoria:** antes de cambiar ejecución, datos, riesgo, dashboard, credenciales o despliegue, se deben leer `data/SYSTEM_MEMORY.md`, `data/PROJECT_CONVERSATION_LOG.md` y este documento. Toda decisión, incidente, evidencia y resultado debe registrarse en los tres.

---

## Hallazgos priorizados

| Prioridad | Hallazgo comprobado | Riesgo | Acción obligatoria |
|---|---|---|---|
| P0 | La liquidación binaria se infiere localmente del precio. | Un resultado y PnL falsos pueden atribuirse a una operación real. | Conservar la estrategia y el selector, pero bloquear órdenes binarias LIVE_REAL y toda liquidación local en modo real hasta disponer de evidencia oficial correlacionada. |
| P0 | Rutas de prueba binarias pueden disparar órdenes. | Una llamada de diagnóstico puede arriesgar fondos. | Desactivar las rutas de prueba real; la API responde 410 sin llamar al motor. |
| P0 | Se borra/acredita estado local antes de confirmación robusta de cierre y hay doble intento de cierre IQ Option. | Saldo/PnL/posición local divergen de la cuenta real. | Máquina de estados, idempotencia y reconciliación. |
| P0 | Uso de `CERT_NONE`/TLS no verificado. | MITM, robo de SSID y ejecución adulterada. | Restaurar verificación TLS y no aceptar certificados inseguros. |
| P0 | `/api/control/get-broker-keys` devuelve contraseña/SSID completos. | Compromiso de la cuenta y órdenes no autorizadas. | Nunca devolver secretos; rotar los actuales y usar secretos de entorno/gestor. |
| P1 | Se envía leverage 500; PnL en vivo/local se calcula con multiplicadores distintos (`500` y `10`). | PnL, sizing y límites de pérdida falsos. | Un único modelo de contrato/margen/PnL, tope conservador y catálogo verificado. |
| P1 | Símbolos inválidos caen a `active_id=1`; OTC se limpia en vez de rechazarse. | Orden sobre EURUSD por error de símbolo. | Allowlist y rechazo explícito sin fallback. |
| P1 | Break-even/trailing se actualizan solo localmente. | El SL remoto puede no estar modificado. | Modificación remota con ACK, reconciliación y alarma. |
| P1 | Feed usa tipos externos, ruido y velas sintéticas cuando falla una fuente. | Señales reales basadas en datos no ejecutables. | Separar feed paper/live y bloquear real por calidad de datos. |
| P1 | Riesgo no calcula pip value, contrato, spread, moneda, margen, riesgo reservado ni pérdida acumulada + nuevo riesgo. | Sobreexposición y corte tardío. | Motor de riesgo determinista pre-trade. |
| P1 | Diario reescribe JSON/CSV, redondea Forex a dos decimales y no persiste IDs/ACKs. | Auditoría, métricas y aprendizaje falsos. | Event store append-only con precisión completa y hash. |
| P1 | Motor inicia automáticamente al importar la app; faltan CSRF y configuración de proxy confiable. | Operación no armada y acciones forjadas. | Armado explícito, CSRF, sesión segura y proxy allowlist. |
| P1 | `deploy_to_vps.sh` usa root, sincroniza y reinicia sin validación/rollback. | Incidente de producción no controlado. | Release aprobado, usuario limitado, backup, health checks y rollback. |
| P2 | Backtest de BTC/vela siguiente sin costos, spread, slippage, intrabar, margen ni walk-forward. | Confianza estadística infundada. | Backtest CFD por eventos con datos IQ Option y validación temporal. |
| P2 | “IA/confianza/Kelly” son heurísticas no calibradas sobre datos potencialmente sintéticos. | Tamaños y decisiones no sustentados estadísticamente. | Calibrar o degradar a filtro explicable; nunca habilitar real por “confianza”. |

---

## Plan de implementación por fases

### Fase 0 — Contención inmediata (P0)

1. Forzar `PAPER` y bloquear `LIVE_REAL` mediante una bandera de liberación explícita (`LIVE_TRADING_ARMED=false` por defecto).
2. Conservar el selector entre `BINARY_OPTIONS` y `FOREX_CFD`, sin mezclar estados, órdenes ni métricas entre productos.
3. Bloquear binarias en LIVE_REAL hasta comprobar liquidaciones oficiales; mantener su análisis y ejecución PAPER.
4. Mantener IQ Option como único broker y rechazar cualquier fallback de binaria a CFD o viceversa.
4. Rotar inmediatamente contraseña y SSID que pudieron estar expuestos por el endpoint.
5. Eliminar devolución de secretos por API. El dashboard solo debe mostrar “configurado/no configurado” y permitir reemplazo, nunca lectura.
6. Restaurar TLS estricto.
7. Deshabilitar actualización/despliegue/reinicio desde el dashboard hasta que exista flujo aprobado.

**Criterio de aceptación Fase 0**
- Rutas de prueba binaria devuelven `410` y no envían órdenes.
- El selector permite cambiar modalidad solo con cartera plana y sin órdenes en tránsito.
- Ninguna operación LIVE_REAL binaria puede abrirse ni liquidarse con precios locales.
- Un símbolo no permitido falla sin abrir WebSocket/orden.
- No existen secretos en respuesta API, HTML, logs o archivos versionados.
- `LIVE_REAL` rechaza toda apertura sin armado administrativo explícito y una lista de comprobaciones verdes.

### Fase 1 — Ejecución, reconciliación y protección del broker

1. Crear tipos explícitos:
   - `OrderIntent`, `BrokerOrder`, `PositionSnapshot`, `ExecutionEvidence`.
2. Máquina de estados persistente:
   - `PENDING_OPEN → OPEN → PENDING_CLOSE → CLOSED`
   - `UNKNOWN` ante timeout/desconexión; bloquea nuevas entradas y exige reconciliación.
3. Toda orden debe tener `client_request_id` UUID persistido antes del envío.
4. Nunca descontar/abonar saldo ni registrar resultado hasta recibir confirmación asociada y reconciliar contra posiciones/balance.
5. Reintentos solo idempotentes; nunca repetir una orden tras timeout sin consultar su estado.
6. Permitir máximo una posición global entre ambas modalidades, incluyendo exposición detectada al arrancar.
7. Usar only allowlist de instrumentos CFD verificables desde el broker. Sin fallback `active_id`.
8. Crear/actualizar/cerrar SL, TP y trailing de forma remota; persistir ACK y valores efectivos devueltos.
9. Emergencia: si no se confirma un cierre, mantener posición `UNKNOWN`, pausar entradas y alertar; no inventar un cierre local.

**Criterio de aceptación Fase 1**
- Pruebas simuladas de ACK, rechazo, timeout, duplicado, desconexión y recuperación.
- Ninguna operación cambia PnL/saldo local antes de evidencia del broker.
- Las pruebas comprueban una sola llamada de cierre por intención.
- Inicio/reinicio reconciliado no abre operaciones si hay una posición o estado incierto.

### Fase 2 — Motor de riesgo IQ Option

1. Sustituir sizing por cálculo basado en:
   - equity reconciliada;
   - precio bid/ask y spread;
   - tamaño de contrato, pip/tick value;
   - distancia real SL;
   - moneda de cuenta/conversión;
   - margen y apalancamiento efectivo;
   - comisión/financiación y buffer de slippage.
2. Límites seguros iniciales, configurables pero no desactivables silenciosamente:
   - riesgo por operación pequeño y expresado como porcentaje/monto;
   - una posición máxima;
   - pérdida máxima diaria por fecha COT/UTC definida;
   - pérdida semanal y drawdown máximo;
   - máximo de intentos/rechazos;
   - máxima exposición por divisa correlacionada.
3. Antes de entrada verificar: `pérdida realizada + riesgo abierto + riesgo nuevo <= límite diario`.
4. Persistir el estado de riesgo y resetear únicamente por fecha de trading definida; prohibido que “limpiar cooldown” borre pérdidas diarias.
5. El apalancamiento es un parámetro de política central con techo conservador; nunca 500 por defecto.

**Criterio de aceptación Fase 2**
- Tests por moneda/contrato, short/long, gaps, spread, stop, margen y límite diario.
- Prueba que impide primera operación si su pérdida estimada supera el límite.
- Dashboard muestra riesgo abierto, pérdida realizada, presupuesto restante y estado de freno.

### Fase 3 — Datos y estrategia verificables

1. Separar `LiveIQOptionMarketData` de `PaperSyntheticMarketData`.
2. En vivo aceptar CFD solo con:
   - símbolo CFD permitido;
   - cotización de IQ Option con bid/ask;
   - timestamp UTC fresco;
   - secuencia válida;
   - velas cerradas.
3. Implementar `DataQualityGate` que bloquee apertura ante stale feed, huecos, spread excesivo, sesión cerrada o divergencia de precio.
4. Retirar aleatoriedad del feed real y etiquetar cada decisión con fuente, timestamp y calidad.
5. Mantener la estrategia como reglas explicables inicialmente. Tratar “confidence” como ranking interno, no probabilidad ni autorización financiera.
6. Aplicar filtro de noticias macro con calendario económico verificable, ventanas antes/después y efecto por par.

**Criterio de aceptación Fase 3**
- Tests donde feed simulado, stale, sin bid/ask y símbolo OTC bloquean live.
- Registro de cada señal con datos exactos, fuente y versión de estrategia.
- No hay operaciones reales durante ventana macro o calidad insuficiente.

### Fase 4 — Investigación cuantitativa y validación

1. Rehacer backtest para CFD IQ Option:
   - OHLC/bid-ask históricos del instrumento;
   - ejecución intrabar conservadora;
   - spread, slippage, financiación, comisiones, margen y stop/gap;
   - reglas idénticas a producción.
2. Dividir por tiempo: entrenamiento, validación y muestra final intacta.
3. Ejecutar walk-forward, análisis de sensibilidad y Monte Carlo de secuencias/ejecución.
4. Medir expectancy neta, profit factor neto, max drawdown, ulcer index, tasa de ruin, estabilidad por pares/régimen y número suficiente de operaciones.
5. Prohibido optimizar parámetros sobre la muestra final; versionar datasets, parámetros, seed y resultados.
6. Pasar por paper trading prolongado con reconciliación; cualquier discrepancia bloquea promoción.

**Criterio de aceptación Fase 4**
- Informe reproducible que no prometa rentabilidad.
- Resultados netos positivos y estables bajo costos conservadores, no solo una métrica.
- Evidencia de paper trading sin discrepancias antes de solicitar aprobación para una prueba real mínima.

### Fase 5 — Seguridad, observabilidad y despliegue

1. CSRF para todos los POST financieros/administrativos; reautenticación para armar real, cambiar riesgo, credenciales y emergencia.
2. No confiar `X-Forwarded-For` salvo proxy configurado.
3. Secretos fuera de JSON de aplicación; permisos mínimos, rotación y redacción de logs.
4. Auditoría append-only con hash encadenado: actor, UTC, configuración, intención, payload redactado, ACK, fill, cierre y reconciliación.
5. Alertas: orden desconocida, discrepancia, SL/TP no confirmado, calidad de feed, límites, excepción del loop y autenticación.
6. Pipeline CI: lint, tests, pruebas negativas P0 y análisis de secretos/dependencias. Las pruebas deben cubrir ambos modos sin prohibir el selector ni vocabulario binario.
7. Despliegue manual aprobado: tag/revisión, backup, migración, pruebas, canary paper, health check y rollback. Sin root ni auto-update por dashboard.

**Criterio de aceptación Fase 5**
- Ningún secreto expuesto en endpoints/logs.
- Toda acción sensible tiene usuario, autorización, CSRF y auditoría.
- Release solo avanza tras checklist firmado y se puede revertir.

---

## Puerta de liberación de LIVE_REAL

La operación real solo podrá considerarse después de todos estos requisitos:

- [ ] Fase 0 a Fase 5 completas con evidencia.
- [ ] Auditoría manual de código sin rutas binarias/OTC/multibroker.
- [ ] Pruebas unitarias, integración y negativas aprobadas.
- [ ] Reconciliación de balance/posiciones comprobada en arranque, orden, stop, TP, timeout y reinicio.
- [ ] Datos IQ Option válidos y bloqueos de calidad demostrados.
- [ ] Paper trading prolongado sin divergencias.
- [ ] Límites de riesgo activos y revisados.
- [ ] Rotación de secretos completada.
- [ ] Aprobación explícita y documentada del usuario para una prueba real mínima y controlada.
- [ ] Plan de rollback y parada de emergencia probado.

---

## Resultado de la auditoría

La arquitectura actual contiene buenas intenciones y algunas pruebas de aislamiento, pero sus garantías son principalmente locales/simuladas. La prioridad no es optimizar señales ni aumentar frecuencia: es **eliminar rutas prohibidas, asegurar la verdad del broker, bloquear datos inválidos y convertir cada regla en una barrera técnica verificable**.
