# Guion de demo — Tether QVAC Track

Documento de uso interno para la presentación. Timing pensado para un slot de **4-5 minutos** (ajustar si el hackathon da más/menos). Todo lo que está en `>` es texto sugerido para decir en voz alta; el resto son acciones/comandos.

---

## 0. Antes de subir al escenario (checklist de 2 minutos)

- [ ] Terminal abierta en la raíz del repo, fuente grande, tema con buen contraste
- [ ] `python -m venv .venv` ya creado e instalado (`pip install -r requirements.txt`) — **no instalar en vivo**
- [ ] Correr `python scripts/generate_sample_data.py` una vez antes de subir (regenera datos frescos, no afecta el timing)
- [ ] Correr `python main.py --ocr-engine mock` una vez en seco para precalentar cachés de Python/imports
- [ ] Tener `reports/reconciliation_report.txt` ya generado como **plan B** (ver sección 5)
- [ ] Wifi/red apagada o modo avión — es un argumento visual fuerte para "offline" (opcional, alto impacto)
- [ ] Tener este archivo (`DEMO.md`) en una segunda pantalla/notas, no en la compartida

---

## 1. El gancho (20 segundos)

> "Cualquier PyME que reconcilia recibos contra su extracto bancario hoy lo hace a mano, o sube fotos de facturas a ChatGPT — algo que la mayoría de los departamentos financieros directamente tiene prohibido por temas de confidencialidad. Nosotros construimos un agente que hace ese trabajo, pero que **nunca necesita internet**: corre 100% en la máquina del usuario, usando el SDK local de Tether QVAC."

Mostrar en pantalla el `README.md` (30% de la pantalla) mientras se habla, sin explicarlo línea por línea.

---

## 2. Arquitectura en una frase (20 segundos)

> "El flujo es simple: recibos (fotos o PDFs) entran por un lado, el extracto bancario en CSV por el otro. Un modelo local de QVAC hace OCR y lee el recibo como si fuera un documento financiero. Pandas cruza esa información contra el banco. Y lo único que sale es una lista de alertas — no un dashboard, no ruido, solo lo que hay que revisar."

Opcional: mostrar el diagrama ASCII del README (`## 2. La solución`) 3-4 segundos, sin detenerse.

---

## 3. Demo en vivo (90-120 segundos) — el corazón de la presentación

### Paso 1 — mostrar los inputs (10s)

```bash
ls data/receipts
```

> "Ocho recibos de muestra — comercios reales, montos reales, algunos con errores a propósito para mostrar qué detecta el agente."

```bash
cat data/bank_statement.csv
```

> "Y este es el extracto bancario simulado, el tipo de export que cualquier banco te da en CSV."

### Paso 2 — correr el agente (30-40s, tiempo real)

```bash
python main.py
```

Mientras corre (2-4 segundos), decir:

> "Esto está usando QVAC en modo automático: intenta el modelo local primero, y si no está disponible en esta máquina, degrada solo a un motor de respaldo — sigue siendo 100% local en cualquier caso."

Cuando termina, **señalar con el mouse/láser** cada bloque de la salida en este orden:

1. El panel superior — "100% offline, ningún dato salió de la máquina"
2. El resumen (matches limpios / críticos / warnings)
3. La tabla de discrepancias — leer en voz alta **una sola** alerta CRITICAL, la de Office Depot:

> "Acá está el caso de uso central: el recibo dice $45.99, el banco cobró $459.90. Es exactamente el tipo de error — un dígito de más — que a mano se pasa por alto y que el agente detecta al toque."

### Paso 3 — un caso más sofisticado (20s)

Señalar la fila `DUPLICATE_RECEIPT` (Shell Gas Station):

> "Este otro caso es más sutil: el mismo recibo fue cargado dos veces. El sistema no lo trata como 'falta en el banco' porque ya sabe que esa transacción fue reclamada por el primer recibo — lo marca como posible duplicado, que es la señal realmente accionable."

### Paso 4 (opcional, si sobra tiempo) — mostrar el reporte en archivo

```bash
cat reports/reconciliation_report.txt
```

> "Y todo esto queda además en un .txt plano — pensado para adjuntar a un mail o archivar como evidencia de auditoría, no solo para mirar en pantalla."

---

## 4. El punto técnico fuerte: por qué es realmente offline (30-40s)

> "La parte que nos importaba resolver bien no era la lógica de matching — es Python y pandas estándar. Lo que nos importaba era que la integración con QVAC fuera real, no un mock. El SDK de Tether levanta un proceso worker local y le habla por RPC en la propia máquina; nosotros mandamos la imagen del recibo como adjunto de un mensaje de chat a un modelo de visión chico que corre en el dispositivo, y le pedimos que transcriba el recibo. Ni un byte de la imagen ni del extracto bancario toca la red en ningún punto del código."

Si preguntan "¿lo probaron con el worker real corriendo?": sí. Instalamos el worker (`npm install -g @qvac/sdk`) y corrimos los 8 recibos con `--ocr-engine qvac` de verdad — conecta, carga el modelo de visión local (SmolVLM2-500M) y transcribe imágenes sin tocar la red. El hallazgo honesto: con ese modelo chico la precisión en OCR estructurado es baja (casi nunca saca el nombre del comercio, alguna vez confunde un ítem con el total). La demo en vivo usa el motor de respaldo por confiabilidad, pero la integración real está probada end-to-end — el diseño con motores intercambiables (`--ocr-engine qvac|tesseract|mock`) es justamente para poder elegir el motor sin tocar el resto del código. Ver README sección "Correr con el worker real de QVAC" para el detalle.

---

## 5. Plan B — si algo falla en vivo

- Si `python main.py` falla o tarda: mostrar directamente `reports/reconciliation_report.txt` ya generado (`cat` o abrirlo en el editor) y seguir el guion igual, ajustando el tiempo verbal ("esto es lo que genera").
- Si preguntan por PDFs multipágina: mencionar que está soportado (`pypdfium2` rasteriza local, sin salir a internet) pero no está en el set de demo por simplicidad — no hace falta demostrarlo en vivo salvo que pregunten específicamente.
- Si preguntan por precisión del OCR real (no el mock): mostrar `tests/test_extractor.py` — ahí están los casos concretos que rompían heurísticas ingenuas (fechas ambiguas DD/MM vs MM/DD, montos sin centavos, nombres de comercio con basura de OCR) y cómo se resolvieron.

---

## 6. Preguntas esperadas del jurado (con respuesta corta preparada)

**"¿Por qué no usar un LLM en la nube, total el usuario podría dar consentimiento?"**
> No es un tema de consentimiento del usuario final — es un requisito de cumplimiento del negocio (SME). Datos financieros con terceros no auditados suele estar directamente prohibido por política interna o por contrato con el banco/procesador de pagos, no es negociable caso por caso.

**"¿Qué tan preciso es el matching?"**
> El umbral de similitud de nombre de comercio es configurable (default 60/100 con RapidFuzz), y normalizamos ruido típico de POS (números de sucursal, referencias largas) antes de comparar. Si el nombre del comercio no llega al umbral pero el monto y la fecha identifican una única transacción sin ambigüedad, igual matchea — pero marcado para revisión manual, nunca adivina si hay más de un candidato posible.

**"¿Cómo escala esto a miles de recibos?"**
> La lógica de matching es O(recibos × transacciones del banco) en el peor caso, filtrado primero por ventana de fecha — para volúmenes de PyME (cientos/miles por mes) es trivial. El cuello de botella real sería el throughput del motor OCR local, no pandas.

**"¿Y si el banco tiene un CSV con columnas distintas?"**
> El loader ya acepta alias comunes de columnas (`transaction_date`, `payee`, `debit`, etc.) y es trivial de extender — es un diccionario de mapeo, no lógica nueva.

---

## 7. Cierre (10s)

> "En resumen: mismo problema que resuelve cualquier herramienta de reconciliación con IA — pero sin que la empresa tenga que elegir entre automatizar y cumplir con sus propias políticas de confidencialidad."
