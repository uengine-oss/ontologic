import pytest

from app.errors import KineticError
from app.mapping import build_call, resolve, validate_params

OP = {"method": "POST", "path": "/equipment/{code}/status"}
CTX = {"this": {"code": "EQ 1/a", "plant": "P1"}, "key": "EQ 1/a", "params": {"reason": "과열"},
       "actor": {"sub": "op1"}, "run_id": "run_1", "plan_id": "pln_1"}


def test_build_call_all_locations():
    call = build_call(OP, {"path.code": "$this.$key", "query.dry": {"$literal": True}, "header.X-Who": "$actor.sub",
                           "body.status": "MAINTENANCE", "body.meta.run": "$run.id", "body.meta.plan": "$plan.id",
                           "body.reason": "$params.reason", "body.count": {"$literal": 3}}, CTX)
    assert call["path"] == "/equipment/EQ%201%2Fa/status"
    assert call["query"] == {"dry": True} and call["headers"] == {"X-Who": "op1"}
    assert call["body"] == {"status": "MAINTENANCE", "meta": {"run": "run_1", "plan": "pln_1"},
                            "reason": "과열", "count": 3}


def test_literals_and_unknown():
    assert resolve("MAINTENANCE", CTX) == "MAINTENANCE"
    assert resolve("$unknown.x", CTX) == "$unknown.x"
    assert resolve({"$literal": {"a": [1]}}, CTX) == {"a": [1]}
    assert resolve("$this.plant", CTX) == "P1"


def test_missing_path_var():
    with pytest.raises(KineticError):
        build_call(OP, {"body.status": "X"}, CTX)


def test_bad_mapping_key():
    with pytest.raises(KineticError):
        build_call(OP, {"cookie.x": "1", "path.code": "$this.code"}, CTX)


def test_validate_params():
    schema = {"type": "object", "properties": {"reason": {"type": "string"}, "level": {"type": "string", "enum": ["a"]}},
              "required": ["reason"]}
    assert validate_params(schema, {"reason": "x"}) == {"reason": "x"}
    for bad in ({}, {"reason": 3}, {"reason": "x", "level": "b"}, []):
        with pytest.raises(KineticError):
            validate_params(schema, bad)
