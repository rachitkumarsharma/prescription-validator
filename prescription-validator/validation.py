"""Reusable validation logic for the Eye Prescription Validator.

The ranges below are application-defined plausibility limits for this demo.
They are NOT universal clinical standards. Change CONFIG to adjust them.
"""
from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

CONFIG = {
    "sph": {"label": "SPH", "min": Decimal("-20.00"), "max": Decimal("20.00")},
    "cyl": {"label": "CYL", "min": Decimal("-10.00"), "max": Decimal("10.00")},
    "step": Decimal("0.25"),
    "axis": {"min": 1, "max": 180},
}
EYES = ("right_eye", "left_eye")

REQUIRED_MSG = "This field is required."
NUMBER_MSG = "Enter a valid finite number."
AXIS_MSG = (
    f"Axis must be an integer between {CONFIG['axis']['min']} and {CONFIG['axis']['max']}."
)
AXIS_REQUIRED_MSG = "Axis is required when CYL is not zero."
SUCCESS_MESSAGE = "Prescription passed all configured validation rules."
FAILURE_MESSAGE = "Please correct the highlighted fields."


class InvalidRequestStructure(ValueError):
    """The request is not shaped like {"right_eye": {...}, "left_eye": {...}}."""


# --- PARSING START ---
# Strict grammar: optional sign, ASCII digits, optional fractional part.
# No exponents, underscores, NaN/Infinity, or non-ASCII digits.
_NUMBER_RE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")
_INTEGER_RE = re.compile(r"[+-]?[0-9]+")
_MAX_LEN = 32


def parse_number(raw: Any) -> Decimal | None:
    """Return a finite Decimal, or None if raw is not a strictly valid number."""
    if isinstance(raw, bool):  # bool is a subclass of int; never treat True as 1
        return None
    if isinstance(raw, int):
        return Decimal(raw)
    if isinstance(raw, float):
        return Decimal(repr(raw)) if math.isfinite(raw) else None
    if isinstance(raw, str):
        text = raw.strip()
        if len(text) <= _MAX_LEN and _NUMBER_RE.fullmatch(text):
            return Decimal(text)
    return None


def parse_integer(raw: Any) -> int | None:
    """Return an int, or None if raw is not a strictly valid integer."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw) if math.isfinite(raw) and raw.is_integer() else None
    if isinstance(raw, str):
        text = raw.strip()
        if len(text) <= _MAX_LEN and _INTEGER_RE.fullmatch(text):
            return int(text)
    return None
# --- PARSING END ---


def is_blank(raw: Any) -> bool:
    return raw is None or (isinstance(raw, str) and raw.strip() == "")


def validate_number_field(raw: Any, rule: Mapping[str, Any]) -> tuple[Decimal | None, str | None]:
    """Validate SPH or CYL. Returns (value, error); exactly one is None."""
    label = rule["label"]
    if is_blank(raw):
        return None, REQUIRED_MSG
    value = parse_number(raw)
    if value is None:
        return None, NUMBER_MSG
    if value < rule["min"] or value > rule["max"]:
        return None, f"{label} must be between {rule['min']:+.2f} and {rule['max']:+.2f}."
    if value != value.quantize(Decimal("0.01")):
        return None, f"{label} may have at most two decimal places."
    if value % CONFIG["step"] != 0:
        return None, f"{label} must be in steps of {CONFIG['step']}."
    return value, None


def validate_axis(raw: Any) -> str | None:
    value = parse_integer(raw)
    if value is None or not (CONFIG["axis"]["min"] <= value <= CONFIG["axis"]["max"]):
        return AXIS_MSG
    return None


def validate_eye(eye: Mapping[str, Any]) -> dict[str, str]:
    """Validate one eye. Returns {field: message} for every detectable error."""
    errors: dict[str, str] = {}

    _, err = validate_number_field(eye.get("sph"), CONFIG["sph"])
    if err:
        errors["sph"] = err

    cyl, err = validate_number_field(eye.get("cyl"), CONFIG["cyl"])
    if err:
        errors["cyl"] = err

    axis_raw = eye.get("axis")
    axis_required = cyl is not None and cyl != 0
    if is_blank(axis_raw):
        if axis_required:
            errors["axis"] = AXIS_REQUIRED_MSG
    else:  # if provided, it must be valid, even when CYL is zero
        err = validate_axis(axis_raw)
        if err:
            errors["axis"] = err
    return errors


def validate_prescription(payload: Any) -> dict[str, str]:
    """Validate both eyes independently. Returns flat {"right_eye.sph": msg, ...}."""
    if not isinstance(payload, Mapping):
        raise InvalidRequestStructure(
            "Request body must be a JSON object containing right_eye and left_eye."
        )
    errors: dict[str, str] = {}
    for eye_key in EYES:
        eye = payload.get(eye_key)
        if eye is not None and not isinstance(eye, Mapping):
            raise InvalidRequestStructure(f"'{eye_key}' must be a JSON object.")
        for field, msg in validate_eye(eye or {}).items():
            errors[f"{eye_key}.{field}"] = msg
    return errors


def build_result(errors: Mapping[str, str]) -> dict[str, Any]:
    if errors:
        return {"valid": False, "message": FAILURE_MESSAGE, "errors": dict(errors)}
    return {"valid": True, "message": SUCCESS_MESSAGE, "errors": {}}
