import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import app  # noqa: E402

client = TestClient(app)


def eye(sph="-2.00", cyl="-0.50", axis="90"):
    return {"sph": sph, "cyl": cyl, "axis": axis}


def rx(right=None, left=None):
    return {"right_eye": right or eye(), "left_eye": left or eye("1.25", "-0.75", "180")}


def post(payload):
    return client.post("/api/validate", json=payload)


def errors_of(payload):
    r = post(payload)
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False
    return body["errors"]


# 1. valid prescriptions
def test_valid_mixed_signs():
    r = post(rx())
    assert r.status_code == 200
    assert r.json() == {
        "valid": True,
        "message": "Prescription passed all configured validation rules.",
        "errors": {},
    }


def test_valid_all_positive_and_boundaries():
    r = post(rx(eye("20", "10", "1"), eye("-20.00", "-10.00", "180")))
    assert r.json()["valid"] is True


def test_numeric_json_values_are_accepted():
    assert post(rx(eye(-2.0, -0.5, 90), eye(1.25, -0.75, 180))).json()["valid"] is True


# 2-5. ranges
@pytest.mark.parametrize("field,value,msg", [
    ("sph", "-20.25", "SPH must be between -20.00 and +20.00."),
    ("sph", "20.25", "SPH must be between -20.00 and +20.00."),
    ("cyl", "-10.25", "CYL must be between -10.00 and +10.00."),
    ("cyl", "10.25", "CYL must be between -10.00 and +10.00."),
])
def test_range_errors(field, value, msg):
    e = eye()
    e[field] = value
    assert errors_of(rx(right=e))[f"right_eye.{field}"] == msg


# 6-8. axis
@pytest.mark.parametrize("axis", ["0", "181", "-5", "90.5", "90.0", "abc", "1_0"])
def test_axis_invalid(axis):
    errs = errors_of(rx(right=eye(axis=axis)))
    assert errs["right_eye.axis"] == "Axis must be an integer between 1 and 180."


# 9-10. missing / blank
def test_missing_sph():
    errs = errors_of(rx(right={"cyl": "-0.50", "axis": "90"}))
    assert errs == {"right_eye.sph": "This field is required."}


@pytest.mark.parametrize("value", ["", "   ", "\t\n", None])
def test_blank_required_fields(value):
    errs = errors_of(rx(right=eye(sph=value, cyl=value, axis="90")))
    assert errs["right_eye.sph"] == "This field is required."
    assert errs["right_eye.cyl"] == "This field is required."


# 11-12. malformed and non-finite
@pytest.mark.parametrize("value", [
    "abc", "1,5", "--1", "1.2.3", "1e1", "1_0", "0x10", "+-1", "5 5",
    "NaN", "nan", "Infinity", "-Infinity", "inf", "-inf", "\u0663",
])
def test_malformed_and_non_finite_strings(value):
    errs = errors_of(rx(right=eye(sph=value)))
    assert errs["right_eye.sph"] == "Enter a valid finite number."


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_raw_json_non_finite_literals(literal):
    raw = ('{"right_eye": {"sph": %s, "cyl": "0", "axis": ""}, '
           '"left_eye": {"sph": "0", "cyl": "0", "axis": ""}}' % literal)
    r = client.post("/api/validate", content=raw, headers={"Content-Type": "application/json"})
    assert r.status_code == 200
    assert r.json()["errors"]["right_eye.sph"] == "Enter a valid finite number."


def test_wrong_types_do_not_crash():
    errs = errors_of(rx(right=eye(sph=True, cyl=[1], axis={"a": 1})))
    assert errs["right_eye.sph"] == "Enter a valid finite number."
    assert errs["right_eye.cyl"] == "Enter a valid finite number."
    assert errs["right_eye.axis"].startswith("Axis must be")


# 13. increments
@pytest.mark.parametrize("value,msg", [
    ("1.30", "SPH must be in steps of 0.25."),
    ("0.10", "SPH must be in steps of 0.25."),
    ("1.234", "SPH may have at most two decimal places."),
])
def test_increment_and_decimal_places(value, msg):
    assert errors_of(rx(right=eye(sph=value)))["right_eye.sph"] == msg


# 14-15. axis / cyl dependency
def test_zero_cyl_with_blank_axis_is_valid():
    for blank in ("", "  ", None):
        assert post(rx(right=eye(cyl="0.00", axis=blank))).json()["valid"] is True


def test_zero_cyl_axis_missing_key_is_valid():
    assert post(rx(right={"sph": "1.00", "cyl": "0"})).json()["valid"] is True


@pytest.mark.parametrize("axis", ["", None, "   "])
def test_nonzero_cyl_requires_axis(axis):
    errs = errors_of(rx(right=eye(cyl="-0.25", axis=axis)))
    assert errs == {"right_eye.axis": "Axis is required when CYL is not zero."}


def test_axis_missing_key_with_nonzero_cyl():
    errs = errors_of(rx(right={"sph": "1.00", "cyl": "-0.25"}))
    assert errs == {"right_eye.axis": "Axis is required when CYL is not zero."}


def test_invalid_cyl_does_not_add_axis_required_error():
    errs = errors_of(rx(right=eye(cyl="abc", axis="")))
    assert "right_eye.axis" not in errs and "right_eye.cyl" in errs


def test_both_eyes_reported_together():
    errs = errors_of(rx(right=eye(sph="abc", axis="200"), left=eye(cyl="11")))
    assert set(errs) == {"right_eye.sph", "right_eye.axis", "left_eye.cyl"}


# 16. missing eye objects
def test_missing_eye_object_gives_field_errors():
    r = post({"left_eye": eye()})
    assert r.status_code == 200
    errs = r.json()["errors"]
    assert errs == {"right_eye.sph": "This field is required.",
                    "right_eye.cyl": "This field is required."}


def test_empty_object_and_null_eyes():
    assert post({}).json()["valid"] is False
    assert post({"right_eye": None, "left_eye": None}).status_code == 200


# 17. bad bodies
def test_empty_body():
    r = client.post("/api/validate", content=b"")
    assert r.status_code == 400 and r.json()["message"] == "Request body is empty."


def test_malformed_json():
    r = client.post("/api/validate", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400 and r.json()["message"] == "Request body is not valid JSON."


def test_invalid_utf8_body():
    r = client.post("/api/validate", content=b"\xff\xfe\x00", headers={"Content-Type": "application/json"})
    assert r.status_code == 400


@pytest.mark.parametrize("payload", [[], "text", 5, None])
def test_non_object_body(payload):
    import json
    r = client.post("/api/validate", content=json.dumps(payload).encode())
    assert r.status_code == 400
    assert r.json()["valid"] is False and "JSON object" in r.json()["message"]


def test_eye_wrong_type():
    r = post({"right_eye": [1, 2], "left_eye": eye()})
    assert r.status_code == 400 and "right_eye" in r.json()["message"]


def test_oversized_body():
    r = client.post("/api/validate", content=b" " * 20000)
    assert r.status_code == 413


def test_deeply_nested_json_does_not_crash():
    r = client.post("/api/validate", content=b"[" * 100000, headers={"Content-Type": "application/json"})
    assert r.status_code in (400, 413)


# 18. recovery
def test_recovery_after_failures():
    assert post(rx(right=eye(sph="abc"))).json()["valid"] is False
    assert client.post("/api/validate", content=b"garbage").status_code == 400
    assert post(rx()).json()["valid"] is True


# extras
def test_health_index_and_docs():
    assert client.get("/health").json() == {"status": "ok"}
    assert "Eye Prescription Validator" in client.get("/").text
    assert client.get("/docs").status_code == 200
    assert client.get("/static/app.js").status_code == 200
