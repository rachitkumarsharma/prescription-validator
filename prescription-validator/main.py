"""Eye Prescription Validator - single FastAPI app serving API + frontend."""
import json
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from validation import CONFIG, InvalidRequestStructure, build_result, validate_prescription

BASE_DIR = Path(__file__).resolve().parent
MAX_BODY_BYTES = 10_000
log = logging.getLogger("prescription-validator")

app = FastAPI(title="Eye Prescription Validator", version="1.0.0")


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


class ValidationResponse(BaseModel):
    valid: bool
    message: str
    errors: dict[str, str]


def _error_body(message: str) -> dict:
    return {"valid": False, "message": message, "errors": {}}


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content=_error_body(exc.message))


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, exc: Exception):
    log.exception("Unhandled error")  # details stay in the server log only
    return JSONResponse(status_code=500, content=_error_body("Internal server error."))


@app.post("/api/validate", response_model=ValidationResponse)
async def validate(request: Request):
    # Raw body on purpose: malformed/empty values must reach the validation
    # layer and come back as friendly field-level errors, not generic 422s.
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise ApiError(413, "Request body is too large.")
    if not body.strip():
        raise ApiError(400, "Request body is empty.")
    try:
        payload = json.loads(body)
    except (ValueError, RecursionError):  # includes JSONDecodeError/UnicodeDecodeError
        raise ApiError(400, "Request body is not valid JSON.")
    try:
        errors = validate_prescription(payload)
    except InvalidRequestStructure as exc:
        raise ApiError(400, str(exc))
    return build_result(errors)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/config")
async def config():
    """Expose configured ranges so the UI help text never drifts from the rules."""
    return {
        "sph": [str(CONFIG["sph"]["min"]), str(CONFIG["sph"]["max"])],
        "cyl": [str(CONFIG["cyl"]["min"]), str(CONFIG["cyl"]["max"])],
        "step": str(CONFIG["step"]),
        "axis": [CONFIG["axis"]["min"], CONFIG["axis"]["max"]],
    }


app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(BASE_DIR / "static" / "index.html")
