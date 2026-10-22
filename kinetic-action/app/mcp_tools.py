"""MCP 도구 (계약 §4). REST 와 1:1, 같은 서비스 객체를 부른다.

`tools/list` 는 호출자와 무관하게 8개 고정(계약 §4 의 7개 + §9.2 `query_system`). 승인 도구는 일부러 없다 — 에이전트가 스스로
승인하지 못하게. 인증은 바깥 ASGI 래퍼가 하고, 검증된 actor 를 scope 에 넣어 준다.
"""

from __future__ import annotations

import json
import uuid
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, Field

from .errors import KineticError
from .plans import KineticService


class Filter(BaseModel):
    prop: str = Field(description="인스턴스 속성 이름 (예: temp, plant)")
    op: Literal["=", "!=", ">", ">=", "<", "<=", "in", "contains", "starts_with", "is_null", "not_null"]
    value: Any = Field(default=None, description="비교 값. in 은 배열, is_null/not_null 은 생략")


ClassArg = Annotated[str, Field(alias="class", description="온톨로지 클래스 이름 (예: Equipment)")]
OptClassArg = Annotated[str | None, Field(alias="class", description="이 클래스의 액션만")]


def _ok(value: Any) -> CallToolResult:
    text = json.dumps(value, ensure_ascii=False, default=str)
    structured = value if isinstance(value, dict) else {"items": value}
    return CallToolResult(content=[TextContent(type="text", text=text)], structuredContent=structured)


def _err(exc: KineticError) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(exc.body(), ensure_ascii=False))],
                          isError=True)


def _actor(ctx: Context) -> dict:
    req = ctx.request_context.request
    actor = req.scope.get("kinetic_actor") if req is not None else None
    if not actor:
        raise KineticError("unauthenticated", "인증 정보가 없습니다.")
    return actor


def _rid(ctx: Context) -> str:
    req = ctx.request_context.request
    return (req.headers.get("x-request-id") if req is not None else None) or uuid.uuid4().hex


def build_mcp(service: KineticService) -> FastMCP:
    mcp = FastMCP(
        "kinetic-action",
        instructions=(
            "온톨로지 인스턴스에 대한 키네틱 액션 실행기. list_actions 로 쓸 수 있는 액션을 확인하고, "
            "plan_action 으로 대상·정책 판정·호출 미리보기를 받은 뒤 execute_plan 으로 실행한다. "
            "승인이 필요한 plan 은 사람이 Studio 에서 승인해야 실행된다. "
            "실행한 것을 취소·되돌리라는 요청이면 compensate_run 을 쓴다 (역순 보상, 승인 불필요). "
            "계획 전에 현재 값을 확인하려면 query_system(GET 전용)을 쓴다 — 쓰기는 오직 액션으로."
        ),
        stateless_http=True,
        json_response=True,
        streamable_http_path="/mcp",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    async def guard(fn, *args, **kwargs) -> CallToolResult:
        try:
            return _ok(await fn(*args, **kwargs))
        except KineticError as exc:
            return _err(exc)

    async def list_actions(ctx: Context, class_: OptClassArg = None) -> CallToolResult:
        """호출자가 쓸 수 있는 키네틱 액션 목록 (정책의 roles 로 거른다)."""
        async def run():
            return service.list_actions(_actor(ctx), class_)
        return await guard(run)

    async def plan_action(ctx: Context, class_: ClassArg, action: str, where: list[Filter] | None = None,
                          params: dict | None = None) -> CallToolResult:
        """조건(where)에 맞는 인스턴스에 액션을 계획한다 (dry-run: 아무것도 바꾸지 않음).

        결과: allowed(실행될 대상) · denied(정책 거부와 사유) · preview(대상별 호출).
        requires_approval 이 true 면 사람이 Studio 에서 승인해야 한다 — 에이전트는 승인할 수 없다.
        승인 후(또는 승인 불필요 시) execute_plan 으로 실행한다.
        """
        async def run():
            return await service.plan(_actor(ctx), class_, action,
                                      where=[f.model_dump() for f in where or []], params=params, request_id=_rid(ctx))
        return await guard(run)

    async def plan_action_ids(ctx: Context, class_: ClassArg, action: str, ids: list[str],
                              params: dict | None = None) -> CallToolResult:
        """대상 키 목록으로 액션을 계획한다 (plan_action 과 같음, 대상만 키로 지정).

        ids 는 **list_actions 의 key_property 값**이다 (예: 고객 코드 C001). 시스템 레코드 id(UUID)가 아니다.
        plan 의 allowed 가 0건이면 실행을 제안하지 말고 대상 지정을 고친다."""
        async def run():
            return await service.plan(_actor(ctx), class_, action, ids=ids, params=params, request_id=_rid(ctx))
        return await guard(run)

    async def execute_plan(ctx: Context, plan_id: str) -> CallToolResult:
        """plan 을 실행한다. 작성자만 가능. 승인이 필요한데 승인되지 않았으면 approval_required.
        같은 plan 을 다시 실행하면 기존 run 을 돌려준다 (중복 호출 없음)."""
        async def run():
            return await service.execute(_actor(ctx), plan_id, request_id=_rid(ctx))
        return await guard(run)

    async def get_plan(ctx: Context, plan_id: str) -> CallToolResult:
        """plan 상태 조회 (승인 여부 확인용)."""
        async def run():
            _actor(ctx)
            return service.get_plan(plan_id)
        return await guard(run)

    async def list_runs(ctx: Context, limit: int = 10) -> CallToolResult:
        """내가 실행한 최근 run 목록 (최근 것부터: run_id·액션·상태·대상·cancellable).
        「방금 처리한 건 모두 취소」 는 이 목록에서 cancellable 인 run 을 **최근 것부터** 하나씩 compensate_run 한다."""
        async def run():
            return {"items": service.list_runs(_actor(ctx), limit)}
        return await guard(run)

    async def get_run(ctx: Context, run_id: str) -> CallToolResult:
        """run 결과 조회 (대상별·단계별 성공·실패·건너뜀·보상, compensations 는 보상 호출 순서)."""
        async def run():
            _actor(ctx)
            return service.get_run(run_id)
        return await guard(run)

    async def compensate_run(ctx: Context, run_id: str, reason: str | None = None) -> CallToolResult:
        """실행된 run 을 취소한다 — 사용자가 "취소해", "되돌려", "원래대로", "undo", "cancel" 이라고 하면 이 도구를 쓴다.

        성공한 대상을 실행 완료 역순으로 하나씩, 각 대상 안에서는 단계 역순으로 보상 호출한다
        (예: 일정 재배정 원복 → 작업지시 취소 → 설비 상태 복원). 원상 복구 방향이라 사람 승인이 필요 없다
        (plan 작성자 또는 승인자). reason 은 취소 사유로 각 시스템에 전달된다. 같은 run 을 다시 취소하면
        기존 결과를 돌려준다. 결과의 compensations 가 실제 보상 호출 순서다.
        """
        async def run():
            return await service.compensate(_actor(ctx), run_id, reason, request_id=_rid(ctx))
        return await guard(run)

    async def query_system(ctx: Context, system: str, operation_id: str, path_params: dict | None = None,
                           query: dict | None = None) -> CallToolResult:
        """등록된 시스템에서 현재 값을 읽는다 (GET operation 만 — 읽기 전용, 계획·승인 없음).

        액션을 계획하기 전에 상태를 확인할 때 쓴다 (예: 금형 남은 타수, 자재 소요, 작업지시 목록).
        쓰기(상태 변경·생성·취소)는 이 도구로 할 수 없다 — 반드시 list_actions → plan_action → execute_plan.
        GET 이 아닌 operation 이면 not_readonly 오류. path_params 는 경로 변수({model} 등), query 는 쿼리 파라미터.
        결과: {ok, http_status, data, truncated, latency_ms} — 배열은 최대 500개까지(넘으면 truncated=true).
        """
        async def run():
            return await service.query(_actor(ctx), system, operation_id, path_params, query, request_id=_rid(ctx))
        return await guard(run)

    for fn in (list_actions, plan_action, plan_action_ids, execute_plan, get_plan, get_run, list_runs, compensate_run,
               query_system):
        mcp.add_tool(fn)
        if "class_" in fn.__code__.co_varnames[: fn.__code__.co_argcount]:
            # 계약상 인자 이름은 `class`(파이썬 예약어). 스키마는 alias 로 `class` 를 내보내고,
            # 검증 후 넘어오는 `class` 키를 함수 인자 `class_` 로 옮겨 준다.
            tool = mcp._tool_manager._tools[fn.__name__]
            tool.fn = (lambda f: (lambda **kw: f(**{("class_" if k == "class" else k): v for k, v in kw.items()})))(fn)
    return mcp
