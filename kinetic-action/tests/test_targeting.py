import pytest

from app.errors import KineticError
from app.targeting import build_query

CLASSES = {"Equipment"}


def test_basic_query_is_parameterized():
    cypher, params = build_query("Equipment", [{"prop": "temp", "op": ">", "value": 80},
                                               {"prop": "plant", "op": "in", "value": ["P1", "P2"]},
                                               {"prop": "note", "op": "is_null"}], 51, classes=CLASSES,
                                 key_property="code")
    assert cypher == ("MATCH (n:`Equipment`) WHERE n.`temp` > $p0 AND n.`plant` IN $p1 AND n.`note` IS NULL "
                      "RETURN n, elementId(n) AS eid ORDER BY n.`code` LIMIT $limit")
    assert params == {"p0": 80, "p1": ["P1", "P2"], "limit": 51}


def test_value_never_interpolated():
    evil = "x' OR 1=1 //"
    cypher, params = build_query("Equipment", [{"prop": "code", "op": "=", "value": evil}], 5, classes=CLASSES)
    assert evil not in cypher and params["p0"] == evil


def test_ids_and_hangul_prop():
    cypher, params = build_query("Equipment", [{"prop": "온도", "op": ">=", "value": 1}], 3, classes=CLASSES, ids=["a"])
    assert "n.`온도` >= $p0" in cypher and "elementId(n) IN $ids" in cypher and params["ids"] == ["a"]


@pytest.mark.parametrize("prop", ["temp`) DETACH DELETE n //", "a b", "1abc", "", "n.temp", "temp;", None, "x`y"])
def test_bad_prop_rejected(prop):
    with pytest.raises(KineticError) as e:
        build_query("Equipment", [{"prop": prop, "op": "=", "value": 1}], 5, classes=CLASSES)
    assert e.value.code == "invalid_filter"


@pytest.mark.parametrize("op", ["=~", "OR", "> 0 OR 1 =", "like", None, "IS NULL"])
def test_bad_op_rejected(op):
    with pytest.raises(KineticError) as e:
        build_query("Equipment", [{"prop": "temp", "op": op, "value": 1}], 5, classes=CLASSES)
    assert e.value.code == "invalid_filter"


@pytest.mark.parametrize("label", ["Plant", "Equipment`) MATCH (m", "_OntologyModel", ""])
def test_label_must_be_catalog_class(label):
    with pytest.raises(KineticError) as e:
        build_query(label, [], 5, classes=CLASSES)
    assert e.value.code == "invalid_filter"


@pytest.mark.parametrize("f", [
    {"prop": "temp", "op": "in", "value": 3},
    {"prop": "temp", "op": "=", "value": {"$gt": 1}},
    {"prop": "temp", "op": "contains", "value": 3},
    {"prop": "temp", "op": "in", "value": [{"a": 1}]},
    "temp > 80",
])
def test_bad_values_rejected(f):
    with pytest.raises(KineticError):
        build_query("Equipment", [f], 5, classes=CLASSES)
