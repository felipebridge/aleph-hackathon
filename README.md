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
                                 │  archivo .txt)│
                                 └───────────────┘
```

Cada etapa corre localmente. El paso de OCR/NLP usa el `tetherto-qvac-sdk` de Tether, que levanta un **proceso worker local** y se comunica con él por un transporte RPC en el propio equipo — no hay cliente HTTP, ni API key, ni ningún socket de red hacia el exterior en todo el código.

## 3. Inicio rápido

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate        macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# Genera el dataset de demo (8 recibos + un bank_statement.csv)
python scripts/generate_sample_data.py

# Corre el agente
python main.py
```

Con eso alcanza — `main.py` lee `data/receipts/`, cruza la información contra `data/bank_statement.csv`, imprime un reporte de discrepancias con colores en la terminal, y escribe el mismo reporte en `reports/reconciliation_report.txt`.

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
  --ocr-engine auto \            # auto | qvac | tesseract | mock
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

El brief del hackathon describe a QVAC como un motor de OCR + "NLP-to-Finance". El `tetherto-qvac-sdk` instalado (v0.17) expone un cliente de inferencia de LLM local de propósito general en lugar de un único método `run_ocr()`, así que la integración funciona así:

1. `Client()` levanta o se conecta al proceso worker local de QVAC.
2. `load_model(transport, model_src=SMOLVLM2_500M_MULTIMODAL_Q8_0)` carga una sola vez, en el primer uso, un modelo pequeño **con capacidad de visión** que corre en el dispositivo.
3. `completion(transport, model_id=..., history=[{"role": "user", "content": <prompt>, "attachments": [{"path": <imagen del recibo>}]}])` envía la imagen del recibo como adjunto de un mensaje de chat junto con un prompt de transcripción OCR, y devuelve el texto transcripto en una sola llamada de inferencia local — el OCR y la lectura "como documento financiero" pasan juntos, exactamente como describe el brief.

Esto está completamente aislado dentro de `QVACOcrEngine` en `ocr_engine.py`. Todo lo que viene después (`extractor.py`, `matcher.py`, `report.py`) solo ve un `OcrResult(text=...)` plano — cambiar el modelo subyacente, o la versión del SDK de QVAC, nunca toca la lógica de negocio.

Como el SDK es async y el resto de esta CLI es intencionalmente simple/sincrónico, `QVACOcrEngine` mantiene un hilo con su propio event loop en segundo plano y despacha las llamadas ahí, manteniendo el proceso worker y el modelo cargado "calientes" durante toda la corrida en lugar de pagar el costo de arranque por cada archivo.

### Cadena de fallback

`--ocr-engine auto` (el valor por defecto) degrada de forma controlada para que el pipeline se pueda demostrar en cualquier máquina:

```
QVAC (tetherto-qvac-sdk, VLM local en el dispositivo)
  └─▶ Tesseract (pytesseract, binario local)
        └─▶ Mock (sidecar .ocr.txt determinístico — siempre disponible)
```

`scripts/generate_sample_data.py` escribe tanto una imagen de recibo renderizada **como** su sidecar `*.ocr.txt` con el texto real, para cada muestra, así el pipeline completo (extracción → matching → reporte) se puede demostrar incluso en una máquina sin el binario worker de QVAC ni Tesseract instalados.

### Correr con el worker real de QVAC

El paquete `tetherto-qvac-sdk` es solo el cliente Python; el worker que ejecuta los modelos hay que instalarlo aparte (requiere Node/npm):

```bash
npm install -g @qvac/sdk@0.17.1

# Windows (PowerShell):
$env:QVAC_SDK_DIR = "$env:APPDATA\npm\node_modules\@qvac\sdk"
# macOS/Linux:
export QVAC_SDK_DIR="$(npm root -g)/@qvac/sdk"

python main.py --ocr-engine qvac
```

Probado end-to-end en este proyecto: el worker levanta, carga `SMOLVLM2_500M_MULTIMODAL_Q8_0` (con su modelo "projection" pareado vía `model_config={"projectionModelSrc": ...}` — sin él, el worker rechaza los adjuntos con `Media not supported by text-only models`), y transcribe imágenes 100% en el dispositivo.

Para garantizar la velocidad en hardware de consumo durante la hackathon, utilizamos el modelo SMOLVLM2_500M. Si bien permite un flujo 100% offline rápido, identificamos que escalar a modelos de visión más grandes del registry de QVAC mejorará drásticamente la extracción de campos complejos como nombres comerciales.
Es decir: no es que ande mal, es que priorizaron velocidad sobre precisión por el contexto del evento, y ya tienen claro el roadmap para mejorarlo

### Soporte de PDF (facturas multipágina)

Un PDF se rasteriza localmente con `pypdfium2` (bindea el renderer PDFium de Google como wheel nativo — sin binario de sistema tipo Poppler, sin salir de la máquina) antes de llegar a cualquiera de los dos motores reales:

- **QVAC**: cada página rasterizada se adjunta como una imagen más en el mismo mensaje de chat (`attachments` acepta una lista), así el modelo lee el documento completo en una sola llamada de inferencia.
- **Tesseract**: cada página se procesa con `pytesseract.image_to_string()` por separado y los textos se concatenan.

Toda esta lógica está centralizada en `_resolve_attachment_paths()` (`ocr_engine.py`) para que ningún motor duplique el manejo de PDFs.



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
│   ├── ocr_engine.py                # motores OCR: QVAC / Tesseract / mock
│   ├── extractor.py                 # texto OCR -> Receipt estructurado (regex/NLP)
│   ├── bank_loader.py                # CSV del banco -> DataFrame de pandas normalizado
│   ├── matcher.py                    # la lógica de negocio de la reconciliación
│   ├── report.py                     # reporte en terminal (rich) + archivo .txt
│   └── cli.py                        # orquesta el pipeline, argparse
├── scripts/generate_sample_data.py   # genera el dataset de demo
├── data/
│   ├── bank_statement.csv            # extracto bancario simulado
│   └── receipts/                     # 8 recibos de muestra sintéticos + sidecars OCR
├── tests/                            # tests unitarios de pytest (extractor/matcher/banco/OCR)
└── reports/                          # ahí caen los reportes .txt generados
```

## 8. Cómo correr los tests

```bash
pip install -r requirements-dev.txt
pytest
```

Los tests cubren las heurísticas de extracción, el loader/validación del CSV bancario, toda la matriz de reglas de negocio del matcher (match limpio, discrepancia de monto, faltante en el banco, recibo duplicado, cargo sin comprobante, tolerancia de fecha) y la abstracción del motor OCR — todo contra fixtures armadas a mano, sin necesitar I/O ni el SDK.

## 9. Dataset de demo

`scripts/generate_sample_data.py` genera 8 recibos que cubren cada tipo de discrepancia que detecta el matcher:

| # | Recibo | Extracto bancario | Resultado |
|---|---|---|---|
| 01 | Starbucks $4.75 | $4.75 | ✅ match limpio |
| 02 | Office Depot $45.99 | $459.90 | 🔴 `AMOUNT_MISMATCH` |
| 03 | Uber $23.50 | $28.50 | 🔴 `AMOUNT_MISMATCH` |
| 04 | Amazon Web Services $89.00 | — | 🟡 `MISSING_IN_BANK` |
| 05 | Costco Wholesale $152.34 | $152.34 | ✅ match limpio |
| 06 | Delta Air Lines $610.00 (3 días antes) | $610.00 | ✅ match limpio, con nota de fecha |
| 07 | Shell Gas Station $52.00 | $52.00 | ✅ match limpio |
| 08 | Shell Gas Station $52.00 (reenviado) | (ya reclamado) | 🔴 `DUPLICATE_RECEIPT` |
| — | (sin recibo) | Wire Transfer $1,200.00 | 🔴 `UNACCOUNTED_CHARGE` |
| — | (sin recibo) | Vending Co $6.50 | 🟡 `UNACCOUNTED_CHARGE` |

## 10. Cómo extenderlo

- **Esquema del CSV bancario**: `bank_loader.py` ya acepta alias comunes de nombres de columna (`transaction_date`, `payee`, `debit`, ...). Agregá más en `_COLUMN_ALIASES` para el formato de exportación de un banco en particular.
- **Un modelo local distinto**: pasale a `QVACOcrEngine(model_src=...)` cualquier constante de `tetherto.qvac_sdk.models`, o una entrada de registro personalizada, para cambiar el modelo que corre en el dispositivo.
