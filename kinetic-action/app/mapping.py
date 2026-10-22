"""arg_mapping → HTTP 호출. 계약 §1.1.

키 `<위치>.<이름>` (path·query·header·body, body 는 점 경로), 값은 표현식:
`$this.<prop>` · `$this.$key` · `$params.<name>` · `$actor.<claim>` · `$run.id` · `$plan.id`,
`$before.<prop>` (실행 직전 스냅숏) · `$steps.<단계>.response.<점.경로>` (같은 대상의 앞 단계 응답) ·
`$cancel.reason` (보상 매핑), `{"$literal": v}`, 그 밖의 문자열은 리터럴.

미리보기(ctx `preview=True`)에서는 아직 없는 값(`$steps.*`·`$cancel.*`)을 `"<식>"` 문자열로 보여 준다.
"""

from __future__ import annotations

import copy
import re
from typing import Any
from urllib.parse import quote

from .errors import KineticError

_PATH_VAR = re.compile(r"\{([^}]+)\}")
LOCATIONS = ("path", "query", "header", "body")


def placeholder(expr: str) -> str:
    return f"<{expr}>"


def _dig(value: Any, path: list[str]) -> Any:
    for p in path:
        if isinstance(value, dict) and p in value:
            value = value[p]
        elif isinstance(value, list) and p.isdigit() and int(p) < len(value):
            value = value[int(p)]
        else:
            raise KeyError(p)
    return value


def _step_ref(expr: str, ctx: dict) -> Any:
    """`$steps.<단계>.response.<경로>` — 없으면 KineticError (그 단계 호출은 실패로 기록된다)."""
    parts = expr.split(".")
    if len(parts) < 3 or parts[2] != "response":
        raise KineticError("invalid_params", f"'{expr}' 형식 오류 ($steps.<단계>.response.<경로>).")
    if ctx.get("preview"):
        return placeholder(expr)
    steps = ctx.get("steps") or {}
    if parts[1] not in steps:
        raise KineticError("invalid_params", f"'{expr}': 단계 '{parts[1]}' 의 응답이 없습니다.")
    try:
        return _dig(steps[parts[1]], parts[3:])
    except KeyError:
        raise KineticError("invalid_params", f"'{expr}': 응답에 그 경로가 없습니다.") from None


def resolve(expr: Any, ctx: dict) -> Any:
    """ctx = {this, key, params, actor, run_id, plan_id, before, steps:{단계: 응답}, cancel:{reason}, preview}."""
    if isinstance(expr, dict) and "$literal" in expr:
        return copy.deepcopy(expr["$literal"])  # 배열 매핑이 리터럴을 고쳐 써도 카탈로그 원본은 그대로
    if not isinstance(expr, str) or not expr.startswith("$"):
        return expr
    if expr == "$this.$key":
        return ctx.get("key")
    if expr == "$run.id":
        return ctx.get("run_id")
    if expr == "$plan.id":
        return ctx.get("plan_id")
    if expr.startswith("$steps."):
        return _step_ref(expr, ctx)
    if expr.startswith("$cancel."):
        if ctx.get("preview") or ctx.get("cancel") is None:
            return placeholder(expr)
        return ctx["cancel"].get(expr[len("$cancel."):])
    for prefix, src in (("$this.", "this"), ("$params.", "params"), ("$actor.", "actor"), ("$before.", "before")):
        if expr.startswith(prefix):
            return (ctx.get(src) or {}).get(expr[len(prefix):])
    return expr  # `$` 로 시작하지만 알 수 없는 식 → 리터럴


def validate_mapping(mapping: dict) -> None:
    for k in mapping:
        loc, _, name = str(k).partition(".")
        if loc not in LOCATIONS or not name:
            raise KineticError("invalid_params", f"arg_mapping 키 '{k}' 형식 오류 (path|query|header|body.<이름>).")


MAX_INDEX = 999  # 배열 인덱스 상한 (실수로 거대한 배열을 만들지 않게)


def _container(seg: str) -> Any:
    return [] if seg.isdigit() else {}


def _put(root: Any, parts: list[str], value: Any, key: str) -> Any:
    """점 경로에 값을 넣는다. **숫자 세그먼트는 배열 인덱스** (계약 §9.3): `lines.0.productCode`.
    배열은 인덱스까지 None 으로 채워 늘린다. 같은 자리를 객체·배열로 엇갈려 쓰면 invalid_params."""
    if root is None:
        root = _container(parts[0])
    elif type(root) is not type(_container(parts[0])):
        raise KineticError("invalid_params", f"arg_mapping 키 '{key}': body 가 객체·배열로 엇갈립니다.")
    node = root
    for i, seg in enumerate(parts):
        last = i == len(parts) - 1
        nxt = None if last else _container(parts[i + 1])
        if isinstance(node, list):
            if not seg.isdigit() or int(seg) > MAX_INDEX:
                raise KineticError("invalid_params", f"arg_mapping 키 '{key}': '{seg}' 자리는 배열 인덱스(0~{MAX_INDEX})여야 합니다.")
            idx = int(seg)
            node.extend([None] * (idx + 1 - len(node)))
            if last:
                node[idx] = value
            else:
                if node[idx] is None:
                    node[idx] = nxt
                elif type(node[idx]) is not type(nxt):
                    raise KineticError("invalid_params", f"arg_mapping 키 '{key}': 객체·배열 자리가 엇갈립니다.")
                node = node[idx]
        else:
            if last:
                node[seg] = value
            else:
                if seg not in node or node[seg] is None:
                    node[seg] = nxt
                elif not isinstance(node[seg], (dict, list)) or type(node[seg]) is not type(nxt):
                    raise KineticError("invalid_params", f"arg_mapping 키 '{key}': 객체·배열 자리가 엇갈립니다.")
                node = node[seg]
    return root


def build_call(operation: dict, mapping: dict, ctx: dict) -> dict:
    """{method, path, query, headers, body} — base URL 은 dispatch 가 붙인다."""

    validate_mapping(mapping)
    path_vals: dict[str, Any] = {}
    query: dict[str, Any] = {}
    headers: dict[str, str] = {}
    body: Any = None
    for key, expr in mapping.items():
        loc, _, name = key.partition(".")
        value = resolve(expr, ctx)
        if loc == "path":
            path_vals[name] = value
        elif loc == "query":
            if value is not None:
                query[name] = value
        elif loc == "header":
            if value is not None:
                headers[name] = str(value)
        else:
            body = _put(body, name.split("."), value, key)

    def sub(m: re.Match) -> str:
        v = path_vals.get(m.group(1))
        if v is None or v == "":
            raise KineticError("invalid_params", f"경로 변수 '{m.group(1)}' 값이 없습니다.")
        if isinstance(v, str) and v.startswith("<$") and ctx.get("preview"):
            return v  # 미리보기 자리표시는 인코딩하지 않는다 (읽히게)
        return quote(str(v), safe="")

    return {"method": operation["method"], "path": _PATH_VAR.sub(sub, operation["path"]),
            "query": query, "headers": headers, "body": body}


def validate_params(schema: dict, params: Any) -> dict:
    """JSON Schema 최소 검사 — required 와 기본 타입. 에이전트 실수를 plan 단계에서 막는다."""

    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise KineticError("invalid_params", "params 는 객체여야 합니다.")
    for name in schema.get("required") or []:
        if params.get(name) in (None, ""):
            raise KineticError("invalid_params", f"파라미터 '{name}' 이 필요합니다.")
    types = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}
    for name, spec in (schema.get("properties") or {}).items():
        t = types.get((spec or {}).get("type"))
        if name in params and params[name] is not None and t and not isinstance(params[name], t):
            raise KineticError("invalid_params", f"파라미터 '{name}' 타입은 {spec['type']} 이어야 합니다.")
        enum = (spec or {}).get("enum")
        if enum and name in params and params[name] not in enum:
            raise KineticError("invalid_params", f"파라미터 '{name}' 은 {enum} 중 하나여야 합니다.")
    return params
