# Eye Prescription Validator

FastAPI app that validates SPH / CYL / Axis for the right and left eye. One process serves the API and the vanilla HTML/CSS/JS frontend. No database; no patient data is stored.

> **The ranges below are application-defined plausibility limits for this demo, not universal clinical standards.** They live in `CONFIG` in `validation.py`.

## Validation rules

| Field | Min | Max | Rules |
|---|---:|---:|---|
| SPH | -20.00 | +20.00 | finite number, up to 2 decimals, 0.25 steps |
| CYL | -10.00 | +10.00 | finite number, up to 2 decimals, 0.25 steps |
| Axis | 1 | 180 | integer; required only when CYL is non-zero; if supplied with CYL = 0 it must still be valid |

Blank / whitespace / null / missing required fields are errors. Malformed values (`abc`, `1e1`, `1_0`), `NaN`, and `±Infinity` are rejected, never coerced to 0. Negative SPH/CYL are valid. Both eyes are validated independently and every error is returned in one response.

## Run (Windows PowerShell)

```powershell
cd prescription-validator
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
start http://127.0.0.1:8000/
# in a second terminal (venv activated):
python -m pytest -v
```

macOS / Linux:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
python -m pytest -v
```

- App: http://127.0.0.1:8000/  
- Health: http://127.0.0.1:8000/health  
- Swagger: http://127.0.0.1:8000/docs

## API

`POST /api/validate` always returns `{"valid", "message", "errors"}`.
- 200 for any processed request, including invalid prescriptions (errors keyed like `right_eye.sph`).
- 400 empty body / malformed JSON / body is not an object / an eye is not an object. 413 body > 10 KB. 500 returns a generic message; details only go to the server log.
- A *missing* eye object is treated as all-fields-missing and returns 200 with field errors.

The endpoint reads the raw body (instead of a strict Pydantic request model) on purpose, so bad values become friendly field errors rather than generic 422s. Pydantic is used for the response model.

The Axis/CYL inputs are `type="text"` with `inputmode`, not `type="number"`: browsers silently turn `abc` into an empty string in number inputs, which would hide malformed input from the backend.

## Human Review and Engineering Improvement

**Original behavior (first draft).** Numbers were parsed with the standard library directly:

```python
def parse_number(raw):
    try:
        return Decimal(str(raw).strip())
    except InvalidOperation:
        return None

def parse_integer(raw):
    try:
        return int(str(raw).strip())
    except ValueError:
        return None
```

**Problem identified.** Python's `Decimal()` and `int()` accept much more than a plain number:
- `"NaN"` parses successfully, and the next line (`value < min`) raises `InvalidOperation`, so the endpoint returned **HTTP 500** instead of a field error. The same happened for raw JSON `NaN` (Python's `json` accepts it).
- `"Infinity"`, `"inf"` parsed, then produced a misleading "out of range" message instead of "not a finite number".
- `"1_0"` and `"1e1"` were **silently accepted as 10**. `int("1_0")` also gave Axis 10. Non-ASCII digits (Arabic-Indic `٣`) were accepted too.
- `True` / `None` were stringified, so `True` became an error by accident rather than by design.

**Modification.** Replace library-leniency with an explicit grammar and type handling (`validation.py`):

```python
_NUMBER_RE  = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")
_INTEGER_RE = re.compile(r"[+-]?[0-9]+")

def parse_number(raw):
    if isinstance(raw, bool):  return None          # bool is an int subclass
    if isinstance(raw, int):   return Decimal(raw)
    if isinstance(raw, float): return Decimal(repr(raw)) if math.isfinite(raw) else None
    if isinstance(raw, str):
        text = raw.strip()
        if len(text) <= 32 and _NUMBER_RE.fullmatch(text):
            return Decimal(text)
    return None
```
(`parse_integer` got the same treatment; floats are accepted only if finite and integer-valued.)

**Why it is safer / more correct.** Only strings matching a strict ASCII grammar (or finite JSON numbers) are ever converted, so NaN/Infinity can never reach a comparison and crash it, nothing is silently reinterpreted (`1_0`, `1e1`), and every bad value gets the same friendly message: `Enter a valid finite number.`

**Test that demonstrates it.** `test_malformed_and_non_finite_strings` and `test_raw_json_non_finite_literals` (also `test_axis_invalid[1_0]`). Before the change: 15 failures including 3 crashes (HTTP 500) on `NaN`/`Infinity`. After: all pass.

## Tests

`python -m pytest -v` runs 64 tests covering the 18 required areas plus health/index/docs.

## Limitations
- Demo rules only; not clinical guidance.
- No authentication or rate limiting (out of scope).
- Frontend behavior was verified by reading code and by HTTP calls to the live server, not in a real browser (see summary).
