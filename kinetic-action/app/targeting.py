"""구조화 필터 → 파라미터화 Cypher. 계약 §3 규칙.

- 라벨은 카탈로그에 있는 클래스만, 속성명은 정규식으로 검사한 뒤 백틱으로 감싼다.
- 값은 절대 문자열에 넣지 않고 `$p0, $p1 …` 파라미터로만 넘긴다.
- 원문 Cypher 는 받지 않는다.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from .errors import KineticError

IDENT_RE = re.compile(r"^[A-Za-z_가-힣][A-Za-z0-9_가-힣]*$")

OPS = {
    "=": "=", "!=": "<>", ">": ">", ">=": ">=", "<": "<", "<=": "<=",
    "in": "IN", "contains": "CONTAINS", "starts_with": "STARTS WITH",
    "is_null": "IS NULL", "not_null": "IS NOT NULL",
}
_UNARY = {"is_null", "not_null"}
_STRING_OPS = {"contains", "starts_with"}
_SCALAR = (str, int, float, bool)


def quote(ident: str, kind: str = "속성") -> str:
    if not isinstance(ident, str) or not IDENT_RE.match(ident):
        raise KineticError("invalid_filter", f"{kind} 이름 '{ident}' 은 허용되지 않습니다.")
    return f"`{ident}`"


def validate_filters(filters: Any) -> list[dict]:
    if filters is None:
        return []
    if not isinstance(filters, list):
        raise KineticError("invalid_filter", "where 는 필터 배열이어야 합니다.")
    out = []
    for f in filters:
        if not isinstance(f, dict):
            raise KineticError("invalid_filter", "필터는 {prop, op, value} 객체여야 합니다.")
        prop, op = f.get("prop"), f.get("op")
        quote(prop)
        if op not in OPS:
            raise KineticError("invalid_filter", f"연산자 '{op}' 은 허용되지 않습니다.")
        value = f.get("value")
        if op in _UNARY:
            value = None
        elif op == "in":
            if not isinstance(value, list) or not all(isinstance(v, _SCALAR) for v in value):
                raise KineticError("invalid_filter", f"'{prop}' in 의 값은 스칼라 배열이어야 합니다.")
        elif op in _STRING_OPS:
            if not isinstance(value, str):
                raise KineticError("invalid_filter", f"'{prop}' {op} 의 값은 문자열이어야 합니다.")
        elif not isinstance(value, _SCALAR):
            raise KineticError("invalid_filter", f"'{prop}' {op} 의 값은 스칼라여야 합니다.")
        out.append({"prop": prop, "op": op, **({} if op in _UNARY else {"value": value})})
    return out


def build_query(label: str, filters: list[dict], limit: int, *, classes: Iterable[str],
                key_property: str | None = None, ids: list[str] | None = None) -> tuple[str, dict]:
    """`MATCH (n:`L`) WHERE … RETURN n, elementId(n) AS eid … LIMIT $limit` 와 파라미터."""

    if label not in set(classes):
        raise KineticError("invalid_filter", f"클래스 '{label}' 은 발행된 클래스가 아닙니다.")
    lbl = quote(label, "클래스")
    filters = validate_filters(filters)
    clauses, params = [], {}
    for i, f in enumerate(filters):
        prop = f"n.{quote(f['prop'])}"
        op = OPS[f["op"]]
        if f["op"] in _UNARY:
            clauses.append(f"{prop} {op}")
        else:
            params[f"p{i}"] = f["value"]
            clauses.append(f"{prop} {op} $p{i}")
    if ids is not None:
        params["ids"] = [str(x) for x in ids]
        clauses.append(f"toString(n.{quote(key_property)}) IN $ids" if key_property else "elementId(n) IN $ids")
    order = f"n.{quote(key_property)}" if key_property else "eid"
    params["limit"] = int(limit)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return f"MATCH (n:{lbl}){where} RETURN n, elementId(n) AS eid ORDER BY {order} LIMIT $limit", params


def match_filter(props: dict, f: dict) -> bool:
    """필터 의미론의 파이썬 구현 — 테스트용 가짜 그래프가 쓴다 (Cypher 와 같은 의미)."""

    v = props.get(f["prop"])
    op, x = f["op"], f.get("value")
    if op == "is_null":
        return v is None
    if op == "not_null":
        return v is not None
    if v is None:
        return False
    try:
        return {
            "=": lambda: v == x, "!=": lambda: v != x, ">": lambda: v > x, ">=": lambda: v >= x,
            "<": lambda: v < x, "<=": lambda: v <= x, "in": lambda: v in x,
            "contains": lambda: isinstance(v, str) and x in v,
            "starts_with": lambda: isinstance(v, str) and v.startswith(x),
        }[op]()
    except TypeError:
        return False
