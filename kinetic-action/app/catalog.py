"""발행된 액션 카탈로그. 그래프(계약 §1)에서 읽어 메모리에 둔다.

JSON 값은 문자열로 직렬화돼 있다(발행 모듈 `_json` 관례). 발행 모듈은 빈 값을 `"[]"` 로
쓰므로 객체 자리의 `[]` 는 빈 객체로 읽는다.

`steps`(계약 §1.3) 가 있으면 다단계(사가) 액션이고 `system`·`operation_id`·`arg_mapping` 은 무시한다.
없으면 그 세 필드로 `main` 단계 하나(보상 없음)를 만든다. steps 가 형식에 맞지 않으면 액션 전체를 무시한다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .graph import GraphReader

log = logging.getLogger("kinetic.catalog")
NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
STEP_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class InvalidSteps(ValueError):
    pass


def _parse(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return default
    if isinstance(default, dict) and value == []:
        return {}
    return value if isinstance(value, type(default)) else default


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class Step:
    name: str
    title: str
    system: str
    operation_id: str
    arg_mapping: dict
    compensation: dict | None = None  # {system, operation_id, arg_mapping}

    def summary(self) -> dict:
        return {"name": self.name, "title": self.title, "system": self.system, "operation_id": self.operation_id,
                "compensable": self.compensation is not None}


def _mapping(value: Any, where: str) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value) if value else {}
        except ValueError:
            raise InvalidSteps(f"{where}: arg_mapping JSON 오류") from None
    if value in (None, []):
        return {}
    if not isinstance(value, dict):
        raise InvalidSteps(f"{where}: arg_mapping 은 객체여야 합니다")
    return value


def parse_steps(raw: Any) -> list[Step]:
    """steps JSON → [Step]. 이름 형식·유일성, 단계마다 system·operation_id 필수. 어기면 InvalidSteps."""
    items = raw if raw not in (None, "") else []
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except ValueError:
            raise InvalidSteps("steps JSON 오류") from None
    if not isinstance(items, list):
        raise InvalidSteps("steps 는 배열이어야 합니다")
    steps: list[Step] = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            raise InvalidSteps(f"steps[{i}] 는 객체여야 합니다")
        name = str(it.get("name") or "")
        if not STEP_NAME_RE.match(name) or any(s.name == name for s in steps):
            raise InvalidSteps(f"steps[{i}].name '{name}' 형식 오류 또는 중복")
        system, op = str(it.get("system") or ""), str(it.get("operation_id") or "")
        if not system or not op:
            raise InvalidSteps(f"steps[{i}] 에 system·operation_id 가 필요합니다")
        comp = it.get("compensation")
        if isinstance(comp, str):
            comp = _parse(comp, None)
        if comp in ({}, [], None):
            comp = None
        elif not isinstance(comp, dict) or not comp.get("operation_id"):
            raise InvalidSteps(f"steps[{i}].compensation 에 operation_id 가 필요합니다")
        else:  # 보상 system 생략 = 그 단계와 같은 시스템
            comp = {"system": str(comp.get("system") or system), "operation_id": str(comp["operation_id"]),
                    "arg_mapping": _mapping(comp.get("arg_mapping"), f"steps[{i}].compensation")}
        steps.append(Step(name=name, title=str(it.get("title") or name), system=system, operation_id=op,
                          arg_mapping=_mapping(it.get("arg_mapping"), f"steps[{i}]"), compensation=comp))
    return steps


@dataclass
class Action:
    class_name: str
    name: str
    schema_id: str = ""
    description: str = ""
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}})
    key_property: str = ""
    system: str = ""
    operation_id: str = ""
    arg_mapping: dict = field(default_factory=dict)
    effect: str = "write"
    confirm_threshold: int = 0
    max_targets: int = 100
    policy: list = field(default_factory=list)
    compensate: str = ""
    writeback_property: str = ""
    version: int = 1
    steps: list[Step] = field(default_factory=list)

    def __post_init__(self):
        if not self.steps:  # 하위 호환: 단일 단계 `main`, 보상 없음
            self.steps = [Step("main", self.name, self.system, self.operation_id,
                               self.arg_mapping)]

    @property
    def systems(self) -> set[str]:
        return {s.system for s in self.steps} | {s.compensation["system"] for s in self.steps if s.compensation}

    @classmethod
    def from_props(cls, p: dict) -> "Action":
        return cls(
            class_name=str(p.get("class_name") or ""),
            name=str(p.get("behavior_name") or ""),
            schema_id=str(p.get("schema_id") or ""),
            description=str(p.get("description") or ""),
            parameters=_parse(p.get("parameters"), {"type": "object", "properties": {}}) or {"type": "object", "properties": {}},
            key_property=str(p.get("key_property") or ""),
            system=str(p.get("system") or ""),
            operation_id=str(p.get("operation_id") or ""),
            arg_mapping=_parse(p.get("arg_mapping"), {}),
            effect=str(p.get("effect") or "write"),
            confirm_threshold=_int(p.get("confirm_threshold"), 0),
            max_targets=_int(p.get("max_targets"), 100),
            policy=_parse(p.get("policy"), []),
            compensate=str(p.get("compensate") or ""),
            writeback_property=str(p.get("writeback_property") or ""),
            version=_int(p.get("version"), 1),
            steps=parse_steps(p.get("steps")),
        )

    def summary(self) -> dict:
        return {
            "class": self.class_name, "action": self.name, "description": self.description,
            "parameters": self.parameters, "effect": self.effect,
            "confirm_threshold": self.confirm_threshold, "max_targets": self.max_targets,
            # plan_action_ids 의 ids 는 이 속성의 값이다 (비면 그래프 elementId) — 레코드 id 를 넘기는 실수를 막는다
            "key_property": self.key_property or "$elementId",
            "system": self.steps[0].system, "operation_id": self.steps[0].operation_id,
            "steps": [s.summary() for s in self.steps],
        }


class Catalog:
    def __init__(self, graph: GraphReader):
        self.graph = graph
        self.actions: dict[tuple[str, str], Action] = {}

    @property
    def classes(self) -> set[str]:
        return {c for c, _ in self.actions}

    def get(self, class_name: str, action: str) -> Action | None:
        return self.actions.get((class_name, action))

    async def refresh(self) -> int:
        rows = await self.graph.load_actions()
        actions: dict[tuple[str, str], Action] = {}
        for row in rows:
            try:
                a = Action.from_props(row)
            except InvalidSteps as exc:
                log.warning("액션 무시(steps): %s.%s — %s", row.get("class_name"), row.get("behavior_name"), exc)
                continue
            if not a.class_name or not NAME_RE.match(a.name):
                log.warning("액션 무시(이름 형식): %s.%s", a.class_name, a.name)
                continue
            prev = actions.get((a.class_name, a.name))
            if prev is None or a.version >= prev.version:  # 같은 이름이 여러 모델에 있으면 높은 버전
                actions[(a.class_name, a.name)] = a
        self.actions = actions
        return len(actions)

    async def run_refresh_loop(self, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                await self.refresh()
            except Exception as exc:  # 그래프가 잠시 내려가도 마지막 카탈로그로 계속 돈다
                log.warning("카탈로그 갱신 실패: %s", exc)
