# Guion de demo — Tether QVAC Track

Documento de uso interno para la presentación. Timing pensado para un slot de **4-5 minutos** (ajustar si el hackathon da más/menos). Todo lo que está en `>` es texto sugerido para decir en voz alta; el resto son acciones/comandos.

**Importante:** el proyecto es una arquitectura híbrida. La inferencia (OCR + matching) corre 100% local vía QVAC, siempre, sin excepción. La ingesta de recibos por WhatsApp Business API sí pasa por la infraestructura de Meta en tránsito — es una decisión consciente, no algo a esconder (ver sección 5). El demo principal (sección 3) usa el modo carpeta local, que sigue siendo 100% offline de punta a punta.

---

## 0. Antes de subir al escenario (checklist — hacer con tiempo, no en el momento)

- [ ] `python -m venv .venv` + `pip install -r requirements.txt` ya hecho
- [ ] Worker de QVAC instalado (`npm install -g @qvac/sdk@0.17.1`) y `QVAC_SDK_DIR` seteado en la sesión que vas a usar en vivo
- [ ] Correr `python main.py` **al menos una vez antes** — la primera corrida descarga el modelo (~2.2 GB), no se puede hacer en vivo
- [ ] Correr `python scripts/generate_sample_data.py` para tener datos frescos
- [ ] Tener `reports/reconciliation_report.txt` de una corrida real ya generado como **plan B** (sección 6)
- [ ] (Si vas a mostrar la sección 5) correr `python scripts/simulate_whatsapp_traffic.py` una vez antes, para tener `data/whatsapp_intake/2026-07/` ya poblado
- [ ] (Opcional, si preguntan por una interfaz sin terminal) `python main_web.py` corriendo en segundo plano, `http://127.0.0.1:8080` ya abierto en una pestaña — ver nota al final del paso 4
- [ ] Wifi/red apagada o modo avión durante la demo en vivo — argumento visual fuerte para "offline" (opcional, alto impacto; **no la apagues si vas a mostrar la sección 5**, ese demo sí simula tráfico de red)
- [ ] Tener este archivo en una segunda pantalla, no en la compartida

---

## 1. El gancho (20 segundos)

> "Pensemos en un estudio contable chico en Argentina — el Estudio Alsina, en Rosario — que le lleva la administración a media docena de PyMEs. Todos los meses, la misma rutina: juntar los comprobantes que cada cliente le manda, casi siempre por WhatsApp y sin ningún orden, y cruzarlos a mano contra el extracto bancario para encontrar errores de facturación o cargos duplicados. Es información financiera de terceros, así que subirla a ChatGPT o cualquier API en la nube directamente no es una opción. Nosotros construimos el agente que automatiza esa rutina para ese estudio, sin que el contenido de los comprobantes salga nunca de su computadora."

Mostrar en pantalla el `README.md` (30% de la pantalla) mientras se habla, sin explicarlo línea por línea.

---

## 2. Arquitectura en una frase (20 segundos)

> "El flujo es simple: recibos, de una carpeta local o mandados por WhatsApp, entran por un lado; el extracto bancario en CSV por el otro. Un modelo de visión especializado en OCR, corriendo local vía QVAC, lee cada recibo. Pandas cruza esa información contra el banco. Y lo único que sale es una lista de alertas — no un dashboard, no ruido, solo lo que hay que revisar."

Opcional: mostrar el diagrama ASCII del README (`## 2. La solución`) 3-4 segundos, sin detenerse.

---

## 3. Demo en vivo — modo carpeta local (90-150 segundos) — el corazón de la presentación

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

> "Esto está mandando cada imagen a un modelo de visión de 3B parámetros especializado en OCR, corriendo en un worker local de QVAC — cero llamadas de red en este modo, se puede ver en el monitor de red si hace falta convencer a alguien."

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

> "Y todo esto queda además en un .txt plano y un .html autocontenido — pensado para adjuntar a un mail o archivar como evidencia de auditoría."

Si preguntan si hay algo sin terminal para alguien no técnico del estudio: mostrar `http://127.0.0.1:8080` (`python main_web.py`) — el mismo formulario, el mismo pipeline, el mismo reporte, sin escribir un solo comando.

---

## 4. El punto técnico fuerte: qué aprendimos probando contra el worker real (30-45s)

> "Lo que nos importaba resolver bien no era la lógica de matching — es Python y pandas estándar. Nos importaba que la integración con QVAC fuera real. El SDK levanta un proceso worker local y le habla por RPC en la propia máquina; mandamos la imagen del recibo como adjunto de un mensaje de chat a un modelo de visión especializado en OCR corriendo en el dispositivo. Lo probamos de verdad, muchas veces, no una sola corrida elegida a dedo — y eso nos hizo encontrar y arreglar cosas reales: un bug donde faltaba parear el modelo con su 'projection model' y el worker rechazaba las imágenes; un prompt demasiado específico que rompía la salida del modelo; y un límite real de ventana de contexto que hace fallar aproximadamente 1 de cada 4 recibos en una sesión larga — lo documentamos como limitación conocida en vez de esconderlo."

Si preguntan "¿por qué no resolvieron el límite de contexto?": lo intentamos (forzar `kv_cache=False` en cada llamada) y **empeoró** los resultados, así que revertimos el cambio y lo dejamos documentado en el README en vez de mandar un fix que no funcionaba.

Si preguntan "¿por qué eligieron ese modelo y no uno más grande?": probamos primero un modelo de chat con visión genérico (SmolVLM2-500M) y casi nunca leía el nombre del comercio; `OCR_3B_MULTIMODAL_Q4_0`, especializado en OCR, fue notablemente mejor en los mismos recibos, y a ~1.7GB entra cómodo en el presupuesto de RAM que marcan las reglas del hackathon.

---

## 5. Bonus (si sobra tiempo, 60-90s) — ingesta por WhatsApp

> "Esto de acá es la parte que resuelve cómo le llegan los recibos al Estudio Alsina en la vida real: por WhatsApp, de uno de sus clientes. No tenemos una cuenta de Meta Business todavía, así que esto es un simulador — pero corre exactamente el mismo código que correría el webhook real, incluyendo el OCR de verdad con QVAC."

```bash
python scripts/simulate_whatsapp_traffic.py
```

> "Esto simula a ese cliente mandando 7 comprobantes reales — Uber, Rappi, PetroSur, y otros — durante julio. Cada uno se procesa al toque y se va guardando en el dataset mensual del estudio."

```bash
python main.py --whatsapp-month 2026-07 --bank-csv data/bank_statement_ar.csv
```

> "Y ahora el estudio reconcilia ese mes acumulado contra el extracto bancario de julio de ese cliente. Fíjense que hay una transferencia y un pago de Mercado Pago en el banco que nadie mandó por WhatsApp — quedan marcados como cargo sin comprobante, exactamente el tipo de cosa que uno quiere que salte."

**Sobre la honestidad de esto (dos cosas, decilas vos antes de que las pregunten):**

1. *¿Sigue siendo 100% offline?* No, y lo decimos nosotros primero: el archivo que manda el cliente pasa por los servidores de Meta en tránsito antes de llegarnos. Es tránsito de mensajería, no inferencia — Meta nunca procesa el contenido financiero — pero técnicamente sale de la red del usuario. La inferencia y el matching siguen siendo 100% locales, siempre. Es una decisión de arquitectura consciente para el caso de uso real, documentada explícitamente en el README (sección 3), no algo que se coló sin querer.
2. *¿Los 7 comprobantes se procesan siempre bien?* No siempre — corriéndolo varias veces nos dio entre 2 y 7 de 7. Estos son PDFs/fotos reales tamaño carta completo (a diferencia de los recibos sintéticos, chicos, de la demo principal), y dos tienen 2 páginas — eso choca más seguido contra el límite de contexto del modelo que ya mencionamos en la sección 4. Es una limitación real del modelo chico con documentos completos reales, la medimos y la documentamos en el README en vez de mostrar solo la corrida que salió bien.

---

## 6. Plan B — si algo falla en vivo

- Si `python main.py` tarda mucho o un recibo falla por límite de contexto: es exactamente el comportamiento documentado (sección 4) — señalarlo como tal ("esto es la limitación que mencioné"), no como un error inesperado, y seguir con los recibos que sí procesó.
- Si el worker no arranca en el escenario: mostrar directamente `reports/reconciliation_report.txt` de una corrida real ya generada (`cat` o abrirlo en el editor) y seguir el guion igual, ajustando el tiempo verbal ("esto es lo que generó en una corrida anterior, en esta misma máquina, con el worker real").
- Si preguntan por PDFs multipágina: mencionar que está soportado (`pypdfium2` rasteriza local, sin salir a internet, cada página se manda como un adjunto más en el mismo mensaje) pero no está en el set de demo por simplicidad.
- Si preguntan por los tests: `tests/test_extractor.py` tiene un test de regresión con la salida real (y ruidosa) que devolvió el modelo en una corrida — bounding boxes, tags de tabla, una oración alucinada — y cómo el pipeline la maneja igual.
- Si la sección 5 falla o no da tiempo: no pasa nada, es "bonus" explícitamente — el demo principal (sección 3) es autocontenido y no depende de ella.

---

## 7. Preguntas esperadas del jurado (con respuesta corta preparada)

**"¿Por qué no usar un LLM en la nube, total el usuario podría dar consentimiento?"**
> No es un tema de consentimiento del usuario final — es un requisito de cumplimiento del negocio (SME). Datos financieros con terceros no auditados suele estar directamente prohibido por política interna o por contrato con el banco/procesador de pagos, no es negociable caso por caso.

**"¿Y lo de WhatsApp no contradice todo el pitch de privacidad?"**
> Es una tensión real y la documentamos como tal, no la escondimos. El OCR y el matching — donde efectivamente se "lee" y procesa la información financiera — son 100% locales siempre, en los dos modos. Lo que cambia con WhatsApp es el transporte del archivo antes de llegar a nuestro proceso, que pasa por Meta. Para quien no tolere ni eso, el modo carpeta local sigue estando, sin ningún cambio, 100% offline.

**"¿Qué tan preciso es el matching?"**
> El umbral de similitud de nombre de comercio es configurable (default 60/100 con RapidFuzz), y normalizamos ruido típico de POS antes de comparar. Si el nombre del comercio no llega al umbral pero el monto y la fecha identifican una única transacción sin ambigüedad, igual matchea — pero marcado para revisión manual, nunca adivina si hay más de un candidato posible. En la práctica, con el modelo de 3B que usamos, la mayoría de los matches en una corrida típica pasan por ese camino, no por coincidencia directa de nombre — y el sistema lo dice explícitamente en vez de esconderlo.

**"¿Cómo escala esto a miles de recibos?"**
> La lógica de matching es O(recibos × transacciones del banco) en el peor caso, filtrado primero por ventana de fecha — para volúmenes de PyME es trivial. El cuello de botella real es el throughput del modelo de visión local, no pandas. Con WhatsApp además el procesamiento es incremental (un recibo a la vez, apenas llega), no un batch mensual gigante.

**"¿Y si el banco tiene un CSV con columnas distintas?"**
> El loader ya acepta alias comunes de columnas (`transaction_date`, `payee`, `debit`, etc.) y es trivial de extender — es un diccionario de mapeo, no lógica nueva.

**"¿Probaron esto con inputs que no eligieron de antemano?"**
> Sí — de hecho el modelo default (OCR_3B) lo elegimos después de comparar dos modelos reales contra los mismos 8 recibos, corriendo el pipeline completo varias veces mientras arreglábamos bugs reales que aparecían (el pareo de projection model, la sensibilidad del prompt, el límite de contexto). No hay ningún camino en el código que devuelva una respuesta pre-escrita.

**"¿Probaron la integración de WhatsApp contra Meta de verdad?"**
> No — no teníamos una cuenta de Meta Business disponible para este proyecto. El código sigue el contrato real y documentado de la Cloud API (formato de webhook, descarga de media en dos pasos, verificación del challenge), pero no está validado en vivo. Lo decimos explícitamente en el README en vez de dar a entender que sí.

**"¿Por qué un estudio contable y no una PyME sola?"**
> Porque es el caso donde el problema es más agudo: una PyME reconcilia sus propios recibos una vez al mes; un estudio contable hace exactamente ese mismo trabajo, multiplicado, para media docena de clientes distintos, con la presión extra de que son datos financieros de terceros bajo secreto profesional. Es el mismo motor de reconciliación — elegimos ese ángulo porque es donde más tiempo se ahorra y donde la privacidad importa más, no porque el producto esté atado a ese nicho específicamente.

---

## 8. Cierre (10s)

> "En resumen: mismo problema que resuelve cualquier herramienta de reconciliación con IA, pero pensado para cómo un estudio contable en Argentina realmente recibe los comprobantes de sus clientes — y siendo honestos en cada punto sobre qué es local, qué no, y qué probamos de verdad contra qué solo en teoría."
