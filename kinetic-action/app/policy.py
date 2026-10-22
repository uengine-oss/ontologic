"""정책 평가. 계약 §1.2.

- 규칙은 OR. 규칙이 없거나 아무것도 맞지 않으면 거부(기본 거부).
- `roles` 비면 모든 인증 사용자. 있으면 actor.roles 와 교집합이 있어야 그 규칙 적용.
- `when` 은 CEL. 평가 오류는 거부(사유 포함). 컴파일 결과는 캐시한다.
- 도구 노출(visible)은 roles 만으로 판정.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import celpy
from celpy.celtypes import BoolType

_env = celpy.Environment()


@lru_cache(maxsize=512)
def _program(expr: str):
    return _env.program(_env.compile(expr))


def _applicable(rule: dict, actor: dict) -> bool:
    roles = rule.get("roles") or []
    return not roles or bool(set(roles) & set(actor.get("roles") or []))


def visible(policy: list, actor: dict) -> bool:
    return any(isinstance(r, dict) and _applicable(r, actor) for r in policy or [])


def _eval_when(expr: str, activation: dict) -> tuple[bool, str | None]:
    try:
        result = _program(expr).evaluate(activation)
    except Exception as exc:
        return False, f"정책 평가 오류({expr}): {str(exc).splitlines()[0][:200]}"
    if not isinstance(result, BoolType):
        return False, f"정책 식이 bool 이 아닙니다({expr})"
    return bool(result), None


def evaluate(policy: list, actor: dict, target: dict, params: dict, now: str) -> tuple[bool, str | None]:
    """(허용 여부, 거부 사유)."""

    rules = [r for r in policy or [] if isinstance(r, dict)]
    if not rules:
        return False, "정책 규칙이 없습니다 (기본 거부)"
    applicable = [r for r in rules if _applicable(r, actor)]
    if not applicable:
        return False, "호출자 역할에 적용되는 정책 규칙이 없습니다"
    activation: dict[str, Any] = {
        "actor": celpy.json_to_cel(actor),
        "target": celpy.json_to_cel(target),
        "params": celpy.json_to_cel(params or {}),
        "now": celpy.json_to_cel(now),
    }
    reasons = []
    for r in applicable:
        expr = (r.get("when") or "").strip()
        if not expr:
            return True, None
        ok, err = _eval_when(expr, activation)
        if ok:
            return True, None
        reasons.append(err or f"조건 불충족: {r.get('description') or expr}")
    return False, "; ".join(reasons)
