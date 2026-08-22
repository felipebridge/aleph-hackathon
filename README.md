# Agente de Reconciliación Financiera con IA (Privacy-First)

**Un agente 100% offline que reconcilia recibos físicos contra un extracto bancario y marca errores de facturación o fraude — sin que un solo byte de información financiera salga de la máquina.**

Construido para el **Tether QVAC Track: Local agents for operations work**.

---

## 1. El problema

Las PyMEs pierden horas cada mes revisando manualmente recibos físicos contra su extracto bancario para detectar errores de facturación, cargos duplicados y fraude. Como los documentos son financieramente sensibles, legal y prácticamente **no pueden** subirse a una API de IA en la nube (OpenAI, Anthropic, etc.) para procesarlos automáticamente.

## 2. La solución

Este agente corre enteramente en la máquina del usuario:

```
data/receipts/*.png,*.jpg,*.pdf         data/bank_statement.csv
        │                                          │
        ▼                                          ▼
  ┌───────────┐   ┌────────────┐   ┌──────────┐   ┌───────────┐
  │ Motor OCR │──▶│ Extractor  │──▶│ Matcher  │◀──│ Bank loader│
  │  (QVAC)   │   │ (regex/NLP)│   │ (pandas +│   │  (pandas)  │
  └───────────┘   └────────────┘   │ rapidfuzz)│   └───────────┘
                                    └────┬─────┘
                                         ▼
                                 ┌───────────────┐
                                 │    Reporte    │
                                 │ (terminal +   │
                                 │  .txt + .html)│
                                 └───────────────┘
```

Cada etapa corre localmente. El paso de OCR/NLP usa el `tetherto-qvac-sdk` de Tether, que levanta un **proceso worker local** y se comunica con él por un transporte RPC en el propio equipo — no hay cliente HTTP, ni API key, ni ningún socket de red hacia el exterior en todo el código.

## 3. Inicio rápido

QVAC es la única capa de inferencia de este proyecto — no hay fallback a ningún otro motor local ni a ninguna API en la nube. Eso significa que además del paquete Python hace falta el **worker** de QVAC (el proceso que corre los modelos), que se instala aparte vía npm. Ver [system requirements](https://docs.qvac.tether.io/system-requirements/) para plataformas soportadas.

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

`main.py` lee `data/receipts/`, hace OCR real de cada imagen con el modelo de visión de QVAC corriendo en el propio dispositivo, cruza esa información contra `data/bank_statement.csv`, imprime un reporte de discrepancias con colores en la terminal, y escribe el mismo reporte en `reports/reconciliation_report.txt` **y** `reports/reconciliation_report.html` (autocontenido, sin dependencias externas, para abrir en el navegador o adjuntar por mail). Si el worker no está instalado o no arranca, el programa **falla con un mensaje explicando cómo instalarlo** — no hay ningún modo silencioso que finja hacer inferencia sin QVAC corriendo.

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
  --date-tolerance-days 3 \      # ventana de tolerancia por demora de acreditación
  --amount-tolerance 0.01 \      # tolerancia en $ antes de considerar los montos "distintos"
  --merchant-threshold 60 \      # sensibilidad del fuzzy-match de nombre de comercio (0-100)
  --large-unmatched-amount 200   # cargos bancarios sin recibo por encima de esto son CRITICAL
```

El proceso termina con código de salida `2` cuando encuentra alguna discrepancia CRITICAL (`0` en caso contrario), así se puede integrar en un cron job o un paso de CI y alertar leyendo `$?`.

## 4. Por qué esto es realmente "offline"

- **OCR/NLP**: el `Client` del `tetherto-qvac-sdk` levanta un proceso worker local (Bare) la primera vez que se usa y se comunica con él por RPC — el modelo corre en el propio dispositivo. Ver [`src/reconciliation_agent/ocr_engine.py`](src/reconciliation_agent/ocr_engine.py).
- **Todo lo demás** (matching con pandas, fuzzy string matching, renderizado del reporte) es cómputo puramente local — no hay I/O más allá de leer los archivos de entrada y escribir el reporte.
- No hay ningún cliente HTTP, API key, ni llamada de telemetría en ningún lugar de `src/`. Buscá `requests`, `httpx`, `urllib` — no vas a encontrar nada.

## 5. La integración con QVAC, explicada

QVAC es la **única** capa de inferencia de este proyecto — no hay ningún otro motor local ni cloud detrás. El `tetherto-qvac-sdk` (v0.17) expone un cliente de inferencia de LLM local de propósito general en lugar de un único método `run_ocr()`, así que la integración funciona así:

1. `Client()` levanta o se conecta al proceso worker local de QVAC (requiere el worker instalado, ver sección 3 — si no está, `get_ocr_engine()` levanta un error explicando cómo instalarlo, nunca degrada en silencio a otra cosa).
2. `load_model(transport, model_src=OCR_3B_MULTIMODAL_Q4_0, model_config={"projectionModelSrc": ...})` carga, una sola vez, un modelo de visión de 3B parámetros del registry de QVAC especializado en OCR, junto con su modelo "projection" pareado (sin él, el worker rechaza los adjuntos con `Media not supported by text-only models`).
3. `completion(transport, model_id=..., history=[{"role": "user", "content": <prompt>, "attachments": [{"path": <imagen del recibo>}]}])` envía la imagen del recibo como adjunto de un mensaje de chat junto con un prompt de transcripción, y devuelve el texto transcripto en una sola llamada de inferencia local.

Esto está completamente aislado dentro de `QVACOcrEngine` en `ocr_engine.py`. Todo lo que viene después (`extractor.py`, `matcher.py`, `report.py`) solo ve un `OcrResult(text=...)` plano — cambiar el modelo subyacente nunca toca la lógica de negocio.

Como el SDK es async y el resto de esta CLI es intencionalmente simple/sincrónico, `QVACOcrEngine` mantiene un hilo con su propio event loop en segundo plano y despacha las llamadas ahí, manteniendo el proceso worker y el modelo cargado "calientes" durante toda la corrida en lugar de pagar el costo de arranque por cada archivo.

### Qué encontramos probando contra el worker real (no simulado)

Todo lo que sigue viene de correr el pipeline completo contra el worker de QVAC de verdad, sobre los 8 recibos de muestra, varias veces, ajustando el código en base a lo que realmente pasaba — no de lo que "debería" pasar en teoría.

- **El modelo importa mucho más que el prompt.** Primero probamos un modelo de visión chico de propósito general (`SMOLVLM2_500M`): cargaba y respondía, pero casi nunca transcribía el nombre del comercio y en un caso confundió un ítem con el TOTAL. `OCR_3B_MULTIMODAL_Q4_0` (~1.7 GB + ~460 MB de projection model), especializado en OCR, es sensiblemente mejor leyendo comercio/fecha/monto en los mismos recibos.
- **Este modelo es sensible a la redacción del prompt de un modo no obvio.** Agregar aclaraciones razonables ("incluí el nombre del comercio, los ítems, el subtotal...") o pedir explícitamente texto plano sin markup rompió la salida por completo (el modelo devolvía una respuesta vacía). El prompt que quedó en `OCR_PROMPT` es deliberadamente minimalista porque es el que funciona, verificado contra el worker real, no una preferencia estética.
- **A veces "filtra" texto que no es la transcripción**: bounding boxes y tags `<table>` propios de su formato de salida (que `extractor.py` limpia con `_strip_layout_markup()`), y ocasionalmente una oración de meta-comentario o preámbulo en vez del nombre del comercio real (`"There is no actual character output to extract."`, `"Transcribe only the following:"`). Agregamos una penalización en el scoring de comercio para oraciones completas terminadas en `.!?`, pero no es infalible — preámbulos que terminan en `:` todavía se cuelan a veces.
- **En sesiones largas, ~1 de cada 4 recibos falla con `prompt exceeds the model's context window`.** Probamos forzar `kv_cache=False` en cada llamada pensando que el problema era reuso de contexto entre archivos — **empeoró los resultados**, así que lo revertimos. Queda documentado como limitación conocida del modelo elegido, no resuelta; el pipeline la maneja bien (ver abajo), no la esconde.

**Por qué esto no rompe la confiabilidad del reporte:** el matcher nunca fuerza un match a partir de un nombre de comercio que no está seguro de haber leído bien.
- Si el comercio no se puede leer con confianza pero el monto+fecha identifican una única transacción posible → matchea igual, pero con una nota explícita de "verificar manualmente" (ver sección 6).
- Si ni siquiera eso alcanza, o si un archivo directamente falla el OCR → el recibo queda flageado, nunca se inventa un match.

Esa es la propiedad que de verdad importa acá: el agente puede tener un OCR imperfecto y aun así nunca reportar con confianza algo que no verificó.

### Soporte de PDF (facturas multipágina)

Un PDF se rasteriza localmente con `pypdfium2` (bindea el renderer PDFium de Google como wheel nativo — sin binario de sistema tipo Poppler, sin salir de la máquina). Cada página rasterizada se adjunta como una imagen más en el mismo mensaje de chat (`attachments` acepta una lista), así QVAC lee el documento completo en una sola llamada de inferencia. Esta lógica vive en `_resolve_attachment_paths()` (`ocr_engine.py`).



## 6. La lógica de negocio (`matcher.py`)

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

## 7. Estructura del proyecto

```
.
├── main.py                          # punto de entrada
├── src/reconciliation_agent/
│   ├── config.py                    # umbrales de negocio configurables
│   ├── models.py                    # Receipt, BankTransaction, Discrepancy, ...
│   ├── ocr_engine.py                # motor OCR: QVAC (única capa de inferencia)
│   ├── extractor.py                 # texto OCR -> Receipt estructurado (regex/NLP)
│   ├── bank_loader.py                # CSV del banco -> DataFrame de pandas normalizado
│   ├── matcher.py                    # la lógica de negocio de la reconciliación
│   ├── report.py                     # reporte en terminal (rich) + archivo .txt
│   ├── report_html.py                # reporte .html autocontenido
│   └── cli.py                        # orquesta el pipeline, argparse
├── scripts/generate_sample_data.py   # genera el dataset de demo
├── data/
│   ├── bank_statement.csv            # extracto bancario simulado
│   └── receipts/                     # 8 imágenes de recibo sintéticas (sin texto pre-cargado)
├── tests/                            # tests unitarios de pytest
└── reports/                          # ahí caen los reportes .txt/.html generados
```

## 8. Cómo correr los tests

```bash
pip install -r requirements-dev.txt
pytest
```

Los tests cubren las heurísticas de extracción (incluyendo montos ARS/AFIP), el loader/validación del CSV bancario, toda la matriz de reglas de negocio del matcher (match limpio, discrepancia de monto, faltante en el banco, recibo duplicado, cargo sin comprobante, tolerancia de fecha), la abstracción del motor OCR, y los reportes .txt/.html — todo contra fixtures armadas a mano, sin necesitar I/O ni el SDK.

## 9. Dataset de demo

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

**Una corrida real observada** (`python main.py`, worker de QVAC real, sin nada pre-cargado): 7/8 recibos procesados (uno falló por el límite de contexto descripto arriba), 3 matches vía el fallback de monto+fecha —el nombre del comercio no se leyó con suficiente claridad en ninguno de los tres, así que cada uno quedó marcado "verificar manualmente" en vez de asumirse correcto—, 2 alertas CRITICAL, 7 WARNING. El caso del duplicado (07/08) es un buen ejemplo de una limitación real: como el OCR garabateó el nombre del comercio distinto en cada uno de los dos recibos, la detección de duplicados (que compara similitud de nombre) no los reconoció como el mismo comercio y ambos terminaron como hallazgos separados en vez de un `DUPLICATE_RECEIPT` — el sistema no inventó una coincidencia que no pudo confirmar, que es el comportamiento correcto aunque no sea el resultado "prolijo" de la tabla de arriba.

## 10. Cómo extenderlo

- **Esquema del CSV bancario**: `bank_loader.py` ya acepta alias comunes de nombres de columna (`transaction_date`, `payee`, `debit`, ...). Agregá más en `_COLUMN_ALIASES` para el formato de exportación de un banco en particular.
- **Un modelo local distinto**: pasale a `QVACOcrEngine(model_src=...)` cualquier constante de `tetherto.qvac_sdk.models`, o una entrada de registro personalizada, para cambiar el modelo que corre en el dispositivo.
- **Otros formatos de recibo/moneda**: `extractor.py` ya reconoce montos en ARS/USD/EUR y sabe limpiar encabezados de facturas AFIP argentinas (`FACTURA`, `ORIGINAL (EJEMPLO)`, `COD. NN`) — mismo patrón para sumar otro formato local de comprobante.
