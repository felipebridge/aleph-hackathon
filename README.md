# Agente de Reconciliación Financiera con IA

**Un agente para el nicho de las PyMEs que reconcilia recibos contra un extracto bancario y marca errores de facturación o fraude. La inferencia (OCR + matching) corre 100% local vía QVAC — nada de eso sale nunca de la máquina. La ingesta de recibos por WhatsApp Business API sí pasa por la infraestructura de Meta en tránsito; ver la sección 3 para el detalle honesto.**

Construido para el **Tether QVAC Track: Local agents for operations work**.

---

## 1. El problema (caso de uso: un estudio contable en Argentina)

Pensalo desde el lado de quien lleva la contabilidad de varias PyMEs, no desde una PyME sola. Un estudio contable chico en Argentina — llamémoslo **Estudio Contable Alsina**, en Rosario — le lleva la administración mensual a media docena de clientes: una empresa de logística, un restaurante, una ferretería. Cada mes, la misma rutina: juntar los comprobantes que cada cliente le manda (casi siempre por WhatsApp, nunca escaneados prolijamente), y cruzarlos a mano contra el extracto bancario de cada uno para encontrar errores de facturación, cargos duplicados o cosas que el banco cobró sin comprobante.

Es trabajo de horas, repetitivo, y con datos financieros de terceros que el estudio no puede mandar alegremente a una API de IA en la nube (OpenAI, Anthropic, etc.) — no es un tecnicismo, es la clase de dato que compromete el secreto profesional del contador y la confianza de sus clientes si se filtra o queda indexado en un tercero. Este proyecto es la herramienta que ese estudio usaría: los clientes le siguen mandando los comprobantes por WhatsApp, como ya hacen hoy, pero todo el procesamiento — leer el comprobante, cruzarlo contra el banco — pasa a ser automático y nunca sale de la computadora del estudio.

## 2. La solución

Dos formas de meter recibos al sistema, un solo motor de reconciliación:

```
                    ┌─────────────────────────┐      ┌──────────────────────────┐
                    │  data/receipts/*.png,   │      │  Cliente manda foto/PDF   │
                    │  *.jpg, *.pdf (local)   │      │  por WhatsApp             │
                    └───────────┬─────────────┘      └────────────┬─────────────┘
                                │                                  │ (vía Meta, cloud)
                                │                     ┌────────────▼─────────────┐
                                │                     │  webhook_server.py        │
                                │                     │  descarga el adjunto,     │
                                │                     │  detecta tipo de archivo  │
                                │                     └────────────┬─────────────┘
                                ▼                                  ▼
                          ┌───────────┐              (ambos caminos convergen acá)
                          │ Motor OCR │◀─────────────────────────────────────────┐
                          │  (QVAC,   │                                          │
                          │  100% local)                                        │
                          └─────┬─────┘                                         │
                                ▼                                               │
                          ┌───────────┐   dataset previsorio mensual            │
                          │ Extractor │──▶ data/whatsapp_intake/<YYYY-MM>/ ──────┘
                          │(regex/NLP)│    (Receipt ya estructurado, JSONL)
                          └─────┬─────┘
                                ▼
      data/bank_statement.csv ─┴──────────▶ ┌──────────┐
      (o *_ar.csv, exportado                │ Matcher  │
       del banco)                           │ (pandas +│
                                             │ rapidfuzz)│
                                             └────┬─────┘
                                                  ▼
                                         ┌───────────────┐
                                         │    Reporte    │
                                         │ (terminal +   │
                                         │  .txt + .html)│
                                         └───────────────┘
```

El extractor, el matcher y los reportes son exactamente los mismos objetos Python (`Receipt`, `ReconciliationResult`) sin importar de dónde vino el archivo — la única diferencia es *cuándo* corre el OCR: al toque cuando llega el mensaje de WhatsApp (y el resultado ya estructurado se guarda), o en el momento de correr `main.py` para una carpeta local.

## 3. Arquitectura híbrida: qué es local y qué no (léelo antes de creer el pitch)

**100% local, siempre:**
- El OCR de cada imagen/PDF — corre en un modelo de visión de QVAC ejecutándose en un worker en tu propia máquina, sin llamadas de red.
- El matching (`matcher.py`) — pandas + RapidFuzz, determinístico, auditable, corre en memoria.
- Los reportes — se escriben a disco local.

**Cloud-mediado, solo en el camino de WhatsApp:**
- Un cliente manda una foto por WhatsApp → ese archivo pasa por los servidores de Meta (WhatsApp Business Cloud API) antes de llegar a `webhook_server.py`. Es tránsito de mensajería, no inferencia — Meta nunca "lee" ni procesa el contenido financiero, solo lo enruta — pero técnicamente el archivo sale de tu red en el camino.
- El único módulo de todo el proyecto que hace una llamada HTTP saliente es [`whatsapp/media_client.py`](src/reconciliation_agent/whatsapp/media_client.py), y es exclusivamente para bajar el adjunto desde la API de Meta. Ningún otro módulo llama a nada por red.

**La decisión consciente:** si tu política de privacidad no tolera ni el tránsito por un tercero, usá solo el modo carpeta local (sección 4) — sigue siendo 100% offline, tal cual arrancó este proyecto. El modo WhatsApp (sección 5) es una capa de ingesta opcional para el caso de uso real de "los clientes mandan comprobantes por WhatsApp", que es como opera la mayoría de las PyMEs en la práctica.

## 4. Modo A — Carpeta local (100% offline)

QVAC es la única capa de inferencia — no hay fallback a ningún otro motor local ni a ninguna API en la nube. Hace falta el **worker** de QVAC además del paquete Python (ver [system requirements](https://docs.qvac.tether.io/system-requirements/)).

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate        macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# Instala el worker de QVAC (requiere Node/npm)
npm install -g @qvac/sdk@0.17.1

# Windows (PowerShell):
$env:QVAC_SDK_DIR = "$env:APPDATA\npm\node_modules\@qvac\sdk"
# macOS/Linux:
export QVAC_SDK_DIR="$(npm root -g)/@qvac/sdk"

# Genera el dataset de demo (8 recibos + un bank_statement.csv)
python scripts/generate_sample_data.py

# Corre el agente -- la primera vez descarga el modelo de visión (~2.2 GB, una sola vez)
python main.py
```

`main.py` lee `data/receipts/`, hace OCR real de cada imagen con QVAC corriendo en el propio dispositivo, cruza esa información contra `data/bank_statement.csv`, imprime un reporte de discrepancias con colores en la terminal, y escribe el mismo reporte en `reports/reconciliation_report.txt` **y** `reports/reconciliation_report.html`. Si el worker no está instalado o no arranca, el programa **falla con un mensaje explicando cómo instalarlo** — no hay ningún modo silencioso que finja hacer inferencia sin QVAC corriendo.

Ejemplo de salida:

```
ALERT: Receipt from 'Office Depot' (02_office_depot.png) indicates $45.99,
but bank statement charged $459.90 (txn TXN-1002, 2026-08-11).
```

### Opciones de la CLI

```
python main.py \
  --receipts-dir data/receipts \
  --bank-csv data/bank_statement.csv \
  --output reports/reconciliation_report.txt \
  --output-html reports/reconciliation_report.html \
  --whatsapp-month 2026-07 \     # alternativa: reconcilia el dataset de WhatsApp de ese mes
  --date-tolerance-days 3 \      # ventana de tolerancia por demora de acreditación
  --amount-tolerance 0.01 \      # tolerancia en $ antes de considerar los montos "distintos"
  --merchant-threshold 60 \      # sensibilidad del fuzzy-match de nombre de comercio (0-100)
  --large-unmatched-amount 200   # cargos bancarios sin recibo por encima de esto son CRITICAL
```

El proceso termina con código de salida `2` cuando encuentra alguna discrepancia CRITICAL (`0` en caso contrario), así se puede integrar en un cron job o un paso de CI y alertar leyendo `$?`.

## 5. Modo B — Ingesta por WhatsApp Business API

Este es el modo pensado para el Estudio Contable Alsina de la sección 1: uno de sus clientes (una PyME de logística, con gastos típicos de combustible, viajes y delivery) le manda al estudio, por WhatsApp, la foto o el PDF de cada comprobante a medida que lo genera — exactamente como ya hace hoy, sin cambiar de hábito. El agente los va juntando en un **dataset previsorio mensual** (`data/whatsapp_intake/<YYYY-MM>/`), OCR-eados al toque con QVAC, listos para que el estudio los reconcilie contra el extracto bancario de ese cliente cuando quiera cerrar el mes.

### Demo sin API real de WhatsApp

No hace falta tener una cuenta de Meta Business para probar el flujo completo. El simulador manda mensajes falsos (con recibos argentinos reales de `data/`, no inventados) a través del mismo código que usa el webhook real:

```bash
python scripts/simulate_whatsapp_traffic.py
```

Esto simula al cliente del estudio mandando 7 comprobantes reales (Uber, Rappi, PetroSur, PedidosYa, LuzSur, Cabify, Express Courier) durante julio 2026, corre OCR real con QVAC sobre cada uno, y los va acumulando en `data/whatsapp_intake/2026-07/`. Después el estudio reconcilia ese mes contra el extracto bancario real del cliente (`data/bank_statement_ar.csv`, que ya incluye esos mismos comercios más una transferencia y un pago de Mercado Pago sin recibo — quedan como `UNACCOUNTED_CHARGE`, a propósito):

```bash
python main.py --whatsapp-month 2026-07 --bank-csv data/bank_statement_ar.csv
```

**Resultado real, corriendo esto varias veces contra el worker de QVAC:** entre 2 y 7 de los 7 comprobantes se procesan según la corrida — a diferencia de los recibos sintéticos de la sección 11 (armados a propósito, chicos y de un renglón), estos son PDFs/fotos reales tamaño carta completo, y dos de ellos (`Uber_receipt_5.pdf`, `Cabify_recibo_1.pdf`) tienen 2 páginas. Eso empuja mucho más seguido contra el límite de ventana de contexto ya documentado en la sección 7 — lo confirmamos inspeccionando esos PDFs directamente (`pypdfium2`, sin QVAC): páginas tamaño 612×792pt, contra el recibo sintético de un renglón que usa la demo principal. Es una limitación real del modelo chico elegido con documentos reales completos, no un bug del código de ingesta, y no la escondemos — para producción, un modelo más grande del registry de QVAC (sección 7) es el camino obvio.

### Setup real (con una cuenta de Meta Business)

1. Creá una app de WhatsApp Business en [Meta for Developers](https://developers.facebook.com/), conseguí un `WHATSAPP_ACCESS_TOKEN` y elegí un `WHATSAPP_VERIFY_TOKEN` propio (cualquier string secreto).
2. Corré el servidor local:
   ```bash
   export WHATSAPP_ACCESS_TOKEN="..."
   export WHATSAPP_VERIFY_TOKEN="..."
   python main_whatsapp.py    # levanta en http://127.0.0.1:8000
   ```
3. Exponelo públicamente para que Meta le pueda pegar (Meta exige HTTPS público, no le sirve `localhost`):
   ```bash
   ngrok http 8000
   ```
4. En la consola de Meta, configurá el webhook apuntando a `https://<tu-url-de-ngrok>/webhook`, con el mismo `WHATSAPP_VERIFY_TOKEN`, y suscribite al campo `messages`.
5. A partir de ahí, cada foto/PDF que te manden por ese número queda procesado y filed en `data/whatsapp_intake/<mes-actual>/` automáticamente.

Ninguna parte de este flujo se probó contra credenciales reales de Meta (no las teníamos disponibles para este proyecto) — el código sigue el contrato real y documentado de la Cloud API de WhatsApp (formato de webhook, descarga de media en dos pasos), pero si algo cambió en la API desde que se escribió, puede necesitar un ajuste.

### Qué archivo hace qué

| Módulo | Rol |
|---|---|
| [`whatsapp/schemas.py`](src/reconciliation_agent/whatsapp/schemas.py) | Parsea el JSON real del webhook de Meta a un `IncomingAttachment` tipado |
| [`whatsapp/file_types.py`](src/reconciliation_agent/whatsapp/file_types.py) | MIME type / filename → extensión, decide si necesita OCR o se descarta |
| [`whatsapp/media_client.py`](src/reconciliation_agent/whatsapp/media_client.py) | El único módulo con salida HTTP: baja el adjunto de la Graph API de Meta |
| [`whatsapp/ingest.py`](src/reconciliation_agent/whatsapp/ingest.py) | Orquesta: guarda el archivo, corre OCR (QVAC), extrae, lo agrega al dataset mensual |
| [`whatsapp/webhook_server.py`](src/reconciliation_agent/whatsapp/webhook_server.py) | FastAPI: verificación de Meta + recepción de mensajes |
| [`whatsapp/simulator.py`](src/reconciliation_agent/whatsapp/simulator.py) | Genera tráfico falso de WhatsApp para demo, sin credenciales |
| [`monthly_dataset.py`](src/reconciliation_agent/monthly_dataset.py) | Persistencia del dataset previsorio mensual (JSONL, un archivo por mes) |

## 6. Modo C — Interfaz web

Una tercera forma de correr todo lo anterior, para quien no quiere usar la terminal: una interfaz web mínima que envuelve el mismo pipeline (`bank_loader`, `ocr_engine`, `extractor`, `matcher`, `report_html`) sin duplicar ninguna lógica de negocio.

```bash
python main_web.py    # levanta en http://127.0.0.1:8080
```

Es un formulario de una sola pantalla: elegís la fuente (carpeta local de recibos, o un mes ya cargado del dataset de WhatsApp) y el CSV del extracto bancario, y al enviar devuelve el mismo reporte HTML que genera la CLI con `--output-html` — mismos colores, misma estructura, con un link para volver y correr otra reconciliación.

Deliberadamente sin framework de JS ni paso de build: un solo archivo ([`webapp.py`](src/reconciliation_agent/webapp.py)) con dos rutas de FastAPI que renderizan HTML server-side, más un poco de JS inline para el toggle entre fuentes y el estado de "procesando" del botón mientras corre el OCR. Corre solo en `127.0.0.1` — nunca se expone a la red — y, como el resto del proyecto, el OCR de la fuente "carpeta local" sigue corriendo 100% vía QVAC en esta misma máquina.

## 7. La integración con QVAC, explicada

QVAC es la **única** capa de inferencia de este proyecto — no hay ningún otro motor local ni cloud detrás. El `tetherto-qvac-sdk` (v0.17) expone un cliente de inferencia de LLM local de propósito general en lugar de un único método `run_ocr()`, así que la integración funciona así:

1. `Client()` levanta o se conecta al proceso worker local de QVAC (si no está instalado, `get_ocr_engine()` levanta un error explicando cómo instalarlo, nunca degrada en silencio a otra cosa).
2. `load_model(transport, model_src=OCR_3B_MULTIMODAL_Q4_0, model_config={"projectionModelSrc": ...})` carga, una sola vez, un modelo de visión de 3B parámetros del registry de QVAC especializado en OCR, junto con su modelo "projection" pareado (sin él, el worker rechaza los adjuntos con `Media not supported by text-only models`).
3. `completion(transport, model_id=..., history=[{"role": "user", "content": <prompt>, "attachments": [{"path": <imagen del recibo>}]}])` envía la imagen del recibo como adjunto de un mensaje de chat junto con un prompt de transcripción, y devuelve el texto transcripto en una sola llamada de inferencia local.

Esto está completamente aislado dentro de `QVACOcrEngine` en `ocr_engine.py`. Todo lo que viene después (`extractor.py`, `matcher.py`, `report.py`) solo ve un `OcrResult(text=...)` plano — cambiar el modelo subyacente nunca toca la lógica de negocio, y es el mismo motor tanto si el archivo vino de una carpeta local como de WhatsApp.

Como el SDK es async y el resto de esta CLI es intencionalmente simple/sincrónico, `QVACOcrEngine` mantiene un hilo con su propio event loop en segundo plano y despacha las llamadas ahí, manteniendo el proceso worker y el modelo cargado "calientes" durante toda la corrida en lugar de pagar el costo de arranque por cada archivo.

### Qué encontramos probando contra el worker real (no simulado)

Todo lo que sigue viene de correr el pipeline completo contra el worker de QVAC de verdad, sobre los 8 recibos de muestra, varias veces, ajustando el código en base a lo que realmente pasaba — no de lo que "debería" pasar en teoría.

- **El modelo importa mucho más que el prompt.** Primero probamos un modelo de visión chico de propósito general (`SMOLVLM2_500M`): cargaba y respondía, pero casi nunca transcribía el nombre del comercio y en un caso confundió un ítem con el TOTAL. `OCR_3B_MULTIMODAL_Q4_0` (~1.7 GB + ~460 MB de projection model), especializado en OCR, es sensiblemente mejor leyendo comercio/fecha/monto en los mismos recibos.
- **Este modelo es sensible a la redacción del prompt de un modo no obvio.** Agregar aclaraciones razonables ("incluí el nombre del comercio, los ítems, el subtotal...") o pedir explícitamente texto plano sin markup rompió la salida por completo (el modelo devolvía una respuesta vacía). El prompt que quedó en `OCR_PROMPT` es deliberadamente minimalista porque es el que funciona, verificado contra el worker real, no una preferencia estética.
- **A veces "filtra" texto que no es la transcripción**: bounding boxes y tags `<table>` propios de su formato de salida (que `extractor.py` limpia con `_strip_layout_markup()`), y ocasionalmente una oración de meta-comentario o preámbulo en vez del nombre del comercio real (`"There is no actual character output to extract."`, `"Transcribe only the following:"`). Agregamos una penalización en el scoring de comercio para oraciones completas terminadas en `.!?`, pero no es infalible — preámbulos que terminan en `:` todavía se cuelan a veces.
- **En sesiones largas, ~1 de cada 4 recibos falla con `prompt exceeds the model's context window`.** Probamos forzar `kv_cache=False` en cada llamada pensando que el problema era reuso de contexto entre archivos — **empeoró los resultados**, así que lo revertimos. Queda documentado como limitación conocida del modelo elegido, no resuelta; el pipeline la maneja bien (ver abajo), no la esconde.

**Por qué esto no rompe la confiabilidad del reporte:** el matcher nunca fuerza un match a partir de un nombre de comercio que no está seguro de haber leído bien.
- Si el comercio no se puede leer con confianza pero el monto+fecha identifican una única transacción posible → matchea igual, pero con una nota explícita de "verificar manualmente" (ver sección 8).
- Si ni siquiera eso alcanza, o si un archivo directamente falla el OCR → el recibo queda flageado, nunca se inventa un match.

Esa es la propiedad que de verdad importa acá: el agente puede tener un OCR imperfecto y aun así nunca reportar con confianza algo que no verificó.

### Soporte de PDF (facturas multipágina)

Un PDF se rasteriza localmente con `pypdfium2` (bindea el renderer PDFium de Google como wheel nativo — sin binario de sistema tipo Poppler, sin salir de la máquina). Cada página rasterizada se adjunta como una imagen más en el mismo mensaje de chat (`attachments` acepta una lista), así QVAC lee el documento completo en una sola llamada de inferencia. Esta lógica vive en `_resolve_attachment_paths()` (`ocr_engine.py`) y la reutilizan tanto el modo carpeta local como el modo WhatsApp.

## 8. La lógica de negocio (`matcher.py`)

Para cada recibo, en orden:

1. Se salta los recibos que el extractor no pudo leer por completo (se marcan para revisión manual en vez de adivinar).
2. Busca transacciones bancarias dentro de `±date_tolerance_days` (la acreditación de la tarjeta suele demorar uno o dos días respecto al recibo) que todavía no hayan sido reclamadas por un recibo anterior.
3. Puntúa la similitud del nombre de comercio con RapidFuzz; descarta todo lo que quede por debajo de `merchant_match_threshold`.
4. Toma el mejor candidato:
   - los montos coinciden dentro de la tolerancia → **match limpio**
   - los montos difieren → **`AMOUNT_MISMATCH`** (CRITICAL) — la alerta principal "el recibo dice $X, el banco cobró $Y"
   - las fechas difieren (dentro de la tolerancia) → se considera match, con una nota aclaratoria
5. No se encuentra ningún candidato → **`MISSING_IN_BANK`**, salvo que parezca el reenvío de un recibo ya matcheado (mismo comercio/monto/fecha), en cuyo caso es la señal más accionable de **`DUPLICATE_RECEIPT`** (CRITICAL).
6. Cualquier transacción bancaria que nadie reclamó → **`UNACCOUNTED_CHARGE`** — dinero que se movió sin recibo en el archivo. CRITICAL por encima de `--large-unmatched-amount`, WARNING por debajo.

Todos los umbrales viven en [`config.py`](src/reconciliation_agent/config.py) como un único dataclass `Settings` — sin números mágicos dispersos por el código de matching.

## 9. Estructura del proyecto

```
.
├── main.py                          # punto de entrada: reconciliación (carpeta local o --whatsapp-month)
├── main_whatsapp.py                 # punto de entrada: servidor del webhook de WhatsApp
├── main_web.py                      # punto de entrada: interfaz web local (ver sección 6)
├── src/reconciliation_agent/
│   ├── config.py                    # umbrales de negocio configurables
│   ├── models.py                    # Receipt, BankTransaction, Discrepancy, ...
│   ├── ocr_engine.py                # motor OCR: QVAC (única capa de inferencia)
│   ├── extractor.py                 # texto OCR -> Receipt estructurado (regex/NLP, ARS/AFIP)
│   ├── bank_loader.py                # CSV del banco -> DataFrame de pandas normalizado
│   ├── matcher.py                    # la lógica de negocio de la reconciliación
│   ├── monthly_dataset.py            # dataset previsorio mensual (JSONL por mes)
│   ├── report.py                     # reporte en terminal (rich) + archivo .txt
│   ├── report_html.py                # reporte .html autocontenido
│   ├── webapp.py                     # interfaz web local (FastAPI, server-rendered)
│   ├── cli.py                        # orquesta el pipeline, argparse
│   └── whatsapp/                     # ingesta por WhatsApp Business Cloud API (ver sección 5)
│       ├── schemas.py                # parseo del webhook real de Meta
│       ├── file_types.py             # MIME/filename -> ¿necesita OCR?
│       ├── media_client.py           # único módulo con salida HTTP (Graph API)
│       ├── ingest.py                 # orquestación: guardar -> OCR -> extraer -> filar
│       ├── webhook_server.py         # FastAPI: GET/POST /webhook
│       └── simulator.py              # demo sin credenciales reales
├── scripts/
│   ├── generate_sample_data.py       # genera el dataset de demo (carpeta local)
│   └── simulate_whatsapp_traffic.py  # genera tráfico de demo (WhatsApp)
├── data/
│   ├── bank_statement.csv            # extracto bancario simulado (demo carpeta local)
│   ├── bank_statement_ar.csv         # extracto bancario simulado (demo WhatsApp, formato AR)
│   ├── receipts/                     # 8 imágenes de recibo sintéticas (demo carpeta local)
│   ├── whatsapp_intake/              # dataset previsorio mensual (se genera en runtime)
│   └── *.pdf, *.jpg                  # recibos argentinos reales (Uber, Rappi, PetroSur, ...)
├── tests/                            # tests unitarios de pytest
└── reports/                          # ahí caen los reportes .txt/.html generados
```

## 10. Cómo correr los tests

```bash
pip install -r requirements-dev.txt
pytest
```

Los tests cubren las heurísticas de extracción (incluyendo montos ARS/AFIP), el loader/validación del CSV bancario, toda la matriz de reglas de negocio del matcher, la abstracción del motor OCR, los reportes .txt/.html, el dataset previsorio mensual, y todo el módulo de WhatsApp (parseo del webhook real de Meta, detección de tipo de archivo, el cliente de media con `httpx.MockTransport`, la orquestación de ingesta, el servidor FastAPI con `TestClient`, y el simulador) — todo con QVAC y la API de Meta mockeados, sin necesitar credenciales ni red.

## 11. Dataset de demo (carpeta local)

`scripts/generate_sample_data.py` genera 8 imágenes de recibo diseñadas para ejercitar cada tipo de discrepancia que detecta el matcher. **A diferencia de una demo con texto pre-cargado, el resultado real de cada corrida depende de lo que QVAC efectivamente lea** — por eso esta tabla describe la intención de cada escenario, no un resultado garantizado:

| # | Recibo | Extracto bancario | Qué ejercita |
|---|---|---|---|
| 01 | Starbucks $4.75 | $4.75 | Match limpio |
| 02 | Office Depot $45.99 | $459.90 | `AMOUNT_MISMATCH` (el banco cobró un dígito de más) |
| 03 | Uber $23.50 | $28.50 | `AMOUNT_MISMATCH` |
| 04 | Amazon Web Services $89.00 | — | `MISSING_IN_BANK` (no hay cargo bancario) |
| 05 | Costco Wholesale $152.34 | $152.34 | Match limpio |
| 06 | Delta Air Lines $610.00 (3 días antes) | $610.00 | Match limpio, con nota de fecha |
| 07 | Shell Gas Station $52.00 | $52.00 | Match limpio |
| 08 | Shell Gas Station $52.00 (reenviado) | (ya reclamado por 07) | `DUPLICATE_RECEIPT` |
| — | (sin recibo) | Wire Transfer $1,200.00 | `UNACCOUNTED_CHARGE` (crítico) |
| — | (sin recibo) | Vending Co $6.50 | `UNACCOUNTED_CHARGE` (warning) |

**Una corrida real observada** (`python main.py`, worker de QVAC real, sin nada pre-cargado): 7/8 recibos procesados (uno falló por el límite de contexto descripto en la sección 7), 3 matches vía el fallback de monto+fecha —el nombre del comercio no se leyó con suficiente claridad en ninguno de los tres, así que cada uno quedó marcado "verificar manualmente" en vez de asumirse correcto—, 2 alertas CRITICAL, 7 WARNING. El caso del duplicado (07/08) es un buen ejemplo de una limitación real: como el OCR garabateó el nombre del comercio distinto en cada uno de los dos recibos, la detección de duplicados no los reconoció como el mismo comercio y ambos terminaron como hallazgos separados en vez de un `DUPLICATE_RECEIPT` — el sistema no inventó una coincidencia que no pudo confirmar, que es el comportamiento correcto aunque no sea el resultado "prolijo" de la tabla de arriba.

<<<<<<< HEAD
## 12. Cómo extenderlo
=======
## 10. Demo con recibos argentinos reales

Además del dataset de muestra, el repo incluye recibos reales argentinos (Uber AR, PeYA, Cabify, PetroSur, LuzSur, Rappi, Express Courier) en `data/receipts_ar/` y un extracto bancario en ARS en `data/bank_statement_ar.csv`:

```bash
python main.py \
  --receipts-dir data/receipts_ar \
  --bank-csv data/bank_statement_ar.csv \
  --output reports/reporte_ar.txt
```

El extractor reconoce automáticamente el formato ARS (`ARS 2,820.00`), limpia encabezados de facturas AFIP (`ORIGINAL (EJEMPLO)`, `COD. 06`, `FACTURA (MUESTRA)`) y extrae fechas en formato DD/MM/YYYY. El extracto incluye una transferencia de $95,000 ARS sin recibo que aparece como `UNACCOUNTED_CHARGE CRITICAL`.

## 11. Cómo extenderlo
>>>>>>> 05572b55a34a3ae37b60accbd19dc36a86222f7a

- **Esquema del CSV bancario**: `bank_loader.py` ya acepta alias comunes de nombres de columna (`transaction_date`, `payee`, `debit`, ...). Agregá más en `_COLUMN_ALIASES` para el formato de exportación de un banco en particular.
- **Un modelo local distinto**: pasale a `QVACOcrEngine(model_src=...)` cualquier constante de `tetherto.qvac_sdk.models`, o una entrada de registro personalizada, para cambiar el modelo que corre en el dispositivo.
- **Otros formatos de recibo/moneda**: `extractor.py` ya reconoce montos en ARS/USD/EUR y sabe limpiar encabezados de facturas AFIP argentinas (`FACTURA`, `ORIGINAL (EJEMPLO)`, `COD. NN`) — mismo patrón para sumar otro formato local de comprobante.
- **Otro canal de mensajería** (Telegram, un formulario web, un buzón de mail): el punto de extensión es `whatsapp/ingest.py::ingest_attachment()` — toma bytes + metadata mínima y hace OCR + fila al dataset mensual; no le importa de dónde vinieron los bytes.
