# Guion de demo — Tether QVAC Track

Documento de uso interno para la presentación. Timing pensado para un slot de **4-5 minutos** (ajustar si el hackathon da más/menos). Todo lo que está en `>` es texto sugerido para decir en voz alta; el resto son acciones/comandos.

**Importante:** QVAC es la única capa de inferencia del proyecto — no hay motor de respaldo. La demo en vivo corre inferencia real, no texto pre-cargado. Eso significa que el resultado exacto puede variar de corrida en corrida (ver sección 4) — el guion está armado para que eso sea parte del argumento, no un riesgo a esconder.

---

## 0. Antes de subir al escenario (checklist — hacer con tiempo, no en el momento)

- [ ] `python -m venv .venv` + `pip install -r requirements.txt` ya hecho
- [ ] Worker de QVAC instalado (`npm install -g @qvac/sdk@0.17.1`) y `QVAC_SDK_DIR` seteado en la sesión que vas a usar en vivo
- [ ] Correr `python main.py` **al menos una vez antes** — la primera corrida descarga el modelo (~2.2 GB), no se puede hacer en vivo
- [ ] Correr `python scripts/generate_sample_data.py` para tener datos frescos
- [ ] Tener `reports/reconciliation_report.txt` de una corrida real ya generado como **plan B** (sección 5)
- [ ] Wifi/red apagada o modo avión durante la demo en vivo — argumento visual fuerte para "offline" (opcional, alto impacto)
- [ ] Tener este archivo en una segunda pantalla, no en la compartida

---

## 1. El gancho (20 segundos)

> "Cualquier PyME que reconcilia recibos contra su extracto bancario hoy lo hace a mano, o sube fotos de facturas a ChatGPT — algo que la mayoría de los departamentos financieros directamente tiene prohibido por temas de confidencialidad. Nosotros construimos un agente que hace ese trabajo, pero que **nunca necesita internet**: corre 100% en la máquina del usuario, con QVAC como única capa de inferencia."

Mostrar en pantalla el `README.md` (30% de la pantalla) mientras se habla, sin explicarlo línea por línea.

---

## 2. Arquitectura en una frase (20 segundos)

> "El flujo es simple: recibos (fotos o PDFs) entran por un lado, el extracto bancario en CSV por el otro. Un modelo de visión especializado en OCR, corriendo local vía QVAC, lee cada recibo. Pandas cruza esa información contra el banco. Y lo único que sale es una lista de alertas — no un dashboard, no ruido, solo lo que hay que revisar."

Opcional: mostrar el diagrama ASCII del README (`## 2. La solución`) 3-4 segundos, sin detenerse.

---

## 3. Demo en vivo (90-150 segundos) — el corazón de la presentación

### Paso 1 — mostrar los inputs (10s)

```bash
ls data/receipts
```

> "Ocho recibos de muestra — comercios reales, montos reales, algunos con errores a propósito para mostrar qué detecta el agente. Ninguno tiene texto pre-cargado: todo lo que se lee, lo lee el modelo en el momento."

```bash
cat data/bank_statement.csv
```

> "Y este es el extracto bancario simulado, el tipo de export que cualquier banco te da en CSV."

### Paso 2 — correr el agente (puede tardar 30-90s, tiempo real de inferencia)

```bash
python main.py
```

Mientras corre, decir:

> "Esto está mandando cada imagen a un modelo de visión de 3B parámetros especializado en OCR, corriendo en un worker local de QVAC — cero llamadas de red, se puede ver en el monitor de red si hace falta convencer a alguien."

Cuando termina, **señalar con el mouse/láser** cada bloque de la salida en este orden:

1. El panel superior — "100% offline, ningún dato salió de la máquina"
2. El resumen (matches limpios / críticos / warnings)
3. La tabla de discrepancias — leer en voz alta la alerta CRITICAL más clara que haya salido en esta corrida (típicamente `AMOUNT_MISMATCH` de Office Depot o Uber, o un `UNACCOUNTED_CHARGE`)

> "Acá está el caso de uso central: un error de facturación que a mano se pasa por alto, detectado automáticamente."

### Paso 3 — el punto que distingue este proyecto de una demo cherry-picked (20-30s)

Buscar en la salida un match reconciliado con la nota "Verify the merchant manually" (va a haber al menos uno — es el comportamiento esperado, no un bug):

> "Miren esto: el modelo no leyó con claridad el nombre del comercio en este recibo, pero el sistema no lo descarta ni inventa un match — lo cruza por monto y fecha, que sí identifican una única transacción posible, y lo marca explícitamente para que un humano lo confirme. Nunca reporta con confianza algo que no pudo verificar."

Esto es más fuerte que mostrar un run perfecto — es la prueba de que el agente maneja OCR real e imperfecto sin mentir sobre su propia certeza.

### Paso 4 (opcional, si sobra tiempo) — mostrar el reporte en archivo

```bash
cat reports/reconciliation_report.txt
```

> "Y todo esto queda además en un .txt plano — pensado para adjuntar a un mail o archivar como evidencia de auditoría."

---

## 4. El punto técnico fuerte: qué aprendimos probando contra el worker real (30-45s)

> "Lo que nos importaba resolver bien no era la lógica de matching — es Python y pandas estándar. Nos importaba que la integración con QVAC fuera real. El SDK levanta un proceso worker local y le habla por RPC en la propia máquina; mandamos la imagen del recibo como adjunto de un mensaje de chat a un modelo de visión especializado en OCR corriendo en el dispositivo. Lo probamos de verdad, muchas veces, no una sola corrida elegida a dedo — y eso nos hizo encontrar y arreglar cosas reales: un bug donde faltaba parear el modelo con su 'projection model' y el worker rechazaba las imágenes; un prompt demasiado específico que rompía la salida del modelo; y un límite real de ventana de contexto que hace fallar aproximadamente 1 de cada 4 recibos en una sesión larga — lo documentamos como limitación conocida en vez de esconderlo."

Si preguntan "¿por qué no resolvieron el límite de contexto?": lo intentamos (forzar `kv_cache=False` en cada llamada) y **empeoró** los resultados, así que revertimos el cambio y lo dejamos documentado en el README en vez de mandar un fix que no funcionaba.

Si preguntan "¿por qué eligieron ese modelo y no uno más grande?": probamos primero un modelo de chat con visión genérico (SmolVLM2-500M) y casi nunca leía el nombre del comercio; `OCR_3B_MULTIMODAL_Q4_0`, especializado en OCR, fue notablemente mejor en los mismos recibos, y a ~1.7GB entra cómodo en el presupuesto de RAM que marcan las reglas del hackathon.

---

## 5. Plan B — si algo falla en vivo

- Si `python main.py` tarda mucho o un recibo falla por límite de contexto: es exactamente el comportamiento documentado (sección 4) — señalarlo como tal ("esto es la limitación que mencioné"), no como un error inesperado, y seguir con los recibos que sí procesó.
- Si el worker no arranca en el escenario: mostrar directamente `reports/reconciliation_report.txt` de una corrida real ya generada (`cat` o abrirlo en el editor) y seguir el guion igual, ajustando el tiempo verbal ("esto es lo que generó en una corrida anterior, en esta misma máquina, con el worker real").
- Si preguntan por PDFs multipágina: mencionar que está soportado (`pypdfium2` rasteriza local, sin salir a internet, cada página se manda como un adjunto más en el mismo mensaje) pero no está en el set de demo por simplicidad.
- Si preguntan por los tests: `tests/test_extractor.py` tiene un test de regresión con la salida real (y ruidosa) que devolvió el modelo en una corrida — bounding boxes, tags de tabla, una oración alucinada — y cómo el pipeline la maneja igual.

---

## 6. Preguntas esperadas del jurado (con respuesta corta preparada)

**"¿Por qué no usar un LLM en la nube, total el usuario podría dar consentimiento?"**
> No es un tema de consentimiento del usuario final — es un requisito de cumplimiento del negocio (SME). Datos financieros con terceros no auditados suele estar directamente prohibido por política interna o por contrato con el banco/procesador de pagos, no es negociable caso por caso.

**"¿Qué tan preciso es el matching?"**
> El umbral de similitud de nombre de comercio es configurable (default 60/100 con RapidFuzz), y normalizamos ruido típico de POS antes de comparar. Si el nombre del comercio no llega al umbral pero el monto y la fecha identifican una única transacción sin ambigüedad, igual matchea — pero marcado para revisión manual, nunca adivina si hay más de un candidato posible. En la práctica, con el modelo de 3B que usamos, la mayoría de los matches en una corrida típica pasan por ese camino, no por coincidencia directa de nombre — y el sistema lo dice explícitamente en vez de esconderlo.

**"¿Cómo escala esto a miles de recibos?"**
> La lógica de matching es O(recibos × transacciones del banco) en el peor caso, filtrado primero por ventana de fecha — para volúmenes de PyME es trivial. El cuello de botella real es el throughput del modelo de visión local, no pandas.

**"¿Y si el banco tiene un CSV con columnas distintas?"**
> El loader ya acepta alias comunes de columnas (`transaction_date`, `payee`, `debit`, etc.) y es trivial de extender — es un diccionario de mapeo, no lógica nueva.

**"¿Probaron esto con inputs que no eligieron de antemano?"**
> Sí — de hecho el modelo default (OCR_3B) lo elegimos después de comparar dos modelos reales contra los mismos 8 recibos, corriendo el pipeline completo varias veces mientras arreglábamos bugs reales que aparecían (el pareo de projection model, la sensibilidad del prompt, el límite de contexto). No hay ningún camino en el código que devuelva una respuesta pre-escrita.

---

## 7. Cierre (10s)

> "En resumen: mismo problema que resuelve cualquier herramienta de reconciliación con IA — pero sin que la empresa tenga que elegir entre automatizar y cumplir con sus propias políticas de confidencialidad, y siendo honesto sobre lo que el modelo local puede y no puede leer bien."
