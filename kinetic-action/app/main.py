"""kinetic-action 진입점 — FastAPI(REST `/api/kinetic`) + MCP(`/mcp`, stateless Streamable HTTP)."""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import logging
import uuid
from typing import Any

import httpx
from fastapi import Body, Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse

from .auth import ROLE_ADMIN, ROLE_APPROVER, Verifier, require_role, resource_metadata, www_authenticate
from .catalog import Catalog
from .config import Settings
from .dispatch import Dispatcher
from .errors import KineticError
from .graph import GraphReader, Neo4jGraph
from .mcp_tools import build_mcp
from .plans import KineticService
from .registry import Registry
from .store import Store

log = logging.getLogger("kinetic")


def _error_response(exc: KineticError, settings: Settings) -> JSONResponse:
    headers = {"WWW-Authenticate": www_authenticate(settings)} if exc.status == 401 else None
    return JSONResponse(exc.body(), status_code=exc.status, headers=headers)


class _Root:
    """`/mcp` 는 인증 후 MCP 세션 매니저로, 나머지는 FastAPI 로 보낸다.

    Mount 대신 직접 분기하는 이유: `/mcp` 와 `/mcp/` 둘 다 리다이렉트 없이 받아야 게이트웨이
    (`/mcp/kinetic/** → /mcp/**`) 뒤에서도 그대로 동작한다.
    """

    def __init__(self, api: FastAPI, mcp, verifier: Verifier, settings: Settings):
        self.api, self.mcp, self.verifier, self.settings = api, mcp, verifier, settings

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] == "http" and (path == "/mcp" or path.startswith("/mcp/")):
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            try:
                actor = self.verifier.from_header(headers.get("authorization"))
            except KineticError as exc:
                await _error_response(exc, self.settings)(scope, receive, send)
                return
            await self.mcp.session_manager.handle_request({**scope, "kinetic_actor": actor}, receive, send)
            return
        await self.api(scope, receive, send)


def create_app(settings: Settings | None = None, *, graph: GraphReader | None = None,
               http: httpx.AsyncClient | None = None, key_resolver=None, refresh_loop: bool = True):
    settings = settings or Settings.from_env()
    graph = graph or Neo4jGraph(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password,
                                settings.neo4j_database)
    http = http or httpx.AsyncClient()
    store = Store(settings.db_url)
    catalog = Catalog(graph)
    registry = Registry(store, http)
    service = KineticService(settings, store, catalog, registry, Dispatcher(settings, http), graph)
    verifier = Verifier(settings, key_resolver)
    mcp = build_mcp(service)
    mcp.streamable_http_app()  # 세션 매니저 생성 (앱 자체는 쓰지 않고 _Root 가 직접 넘긴다)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        try:
            n = await catalog.refresh()
            log.info("카탈로그 적재: 액션 %d개", n)
        except Exception as exc:
            log.warning("카탈로그 초기 적재 실패 (주기 갱신으로 재시도): %s", exc)
        task = asyncio.create_task(catalog.run_refresh_loop(settings.catalog_refresh)) if refresh_loop else None
        async with mcp.session_manager.run():
            yield
        if task:
            task.cancel()
        close = getattr(graph, "close", None)
        if close:
            await close()

    api = FastAPI(title="kinetic-action", version="0.1.0", lifespan=lifespan)
    api.state.service = service
    api.state.settings = settings

    @api.exception_handler(KineticError)
    async def _kinetic_error(_req, exc: KineticError):
        return _error_response(exc, settings)

    @api.middleware("http")
    async def _request_id(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response

    def actor(authorization: str | None = Header(default=None)) -> dict:
        return verifier.from_header(authorization)

    def rid(request: Request) -> str:
        return request.state.request_id

    def internal(x_kinetic_internal: str | None = Header(default=None)) -> None:
        if not settings.internal_secret or not x_kinetic_internal or not hmac.compare_digest(
                x_kinetic_internal, settings.internal_secret):
            raise KineticError("forbidden", "내부 호출 전용입니다 (X-Kinetic-Internal).")

    # ── 공개 ──
    @api.get("/.well-known/oauth-protected-resource")
    @api.get("/.well-known/oauth-protected-resource/mcp")
    async def protected_resource():
        return resource_metadata(settings)

    @api.get("/api/kinetic/health")
    async def health():
        return {"ok": True}

    # ── 서비스 레지스트리 ──
    @api.post("/api/kinetic/systems")
    async def register_system(body: dict = Body(...), who: dict = Depends(actor), request_id: str = Depends(rid)):
        require_role(who, ROLE_ADMIN)
        system = await registry.register(body)
        store.audit("register_system", actor_sub=who["sub"], request_id=request_id, detail={"name": system["name"]})
        return system

    @api.post("/api/kinetic/systems/test")
    async def test_system(body: dict = Body(...), who: dict = Depends(actor)):
        """연결 테스트 — 저장하지 않는다 (계약 §8)."""
        require_role(who, ROLE_ADMIN)
        return await registry.test(body, direct=settings.svc_direct)

    @api.get("/api/kinetic/systems")
    async def list_systems(_: dict = Depends(actor)):
        return registry.list()

    @api.get("/api/kinetic/systems/routes", dependencies=[Depends(internal)])
    async def routes():
        return registry.routes()

    @api.get("/api/kinetic/systems/{name}")
    async def get_system(name: str, _: dict = Depends(actor)):
        return registry.get(name)

    def _admin(who: dict, event: str, request_id: str, **detail) -> None:
        require_role(who, ROLE_ADMIN)
        store.audit(event, actor_sub=who["sub"], request_id=request_id, detail=detail)

    @api.patch("/api/kinetic/systems/{name}")
    async def patch_system(name: str, body: dict = Body(...), who: dict = Depends(actor),
                           request_id: str = Depends(rid)):
        require_role(who, ROLE_ADMIN)
        system = await registry.patch(name, body)
        _admin(who, "update_system", request_id, name=name, fields=sorted(body))
        return system

    @api.delete("/api/kinetic/systems/{name}")
    async def delete_system(name: str, who: dict = Depends(actor), request_id: str = Depends(rid)):
        require_role(who, ROLE_ADMIN)
        registry.delete(name)
        used_by = service.actions_using(name)  # 발행된 액션이 써도 지운다 — 목록만 알려 준다
        _admin(who, "delete_system", request_id, name=name, used_by=used_by)
        return {"deleted": True, "used_by": used_by}

    @api.post("/api/kinetic/systems/{name}/refresh")
    async def refresh_system(name: str, who: dict = Depends(actor), request_id: str = Depends(rid)):
        require_role(who, ROLE_ADMIN)
        system = await registry.refresh(name)
        _admin(who, "refresh_system", request_id, name=name, operations=system["operations_count"])
        return system

    @api.get("/api/kinetic/systems/{name}/health")
    async def system_health(name: str, _: dict = Depends(actor)):
        return await service.dispatcher.health(registry.system(name))

    @api.get("/api/kinetic/systems/{name}/operations")
    async def operations(name: str, request: Request, _: dict = Depends(actor)):
        return registry.operations(name, request.query_params.get("method"))

    @api.post("/api/kinetic/systems/{name}/query")
    async def query_system(name: str, body: dict = Body(...), who: dict = Depends(actor),
                           request_id: str = Depends(rid)):
        """조회 경로 (계약 §9.2) — GET operation 만, 계획·승인 없음."""
        return await service.query(who, name, body.get("operation_id"), body.get("path_params"), body.get("query"),
                                   request_id=request_id)

    @api.post("/api/kinetic/systems/{name}/operations")
    async def add_operation(name: str, body: dict = Body(...), who: dict = Depends(actor),
                            request_id: str = Depends(rid)):
        require_role(who, ROLE_ADMIN)
        op = registry.add_operation(name, body)
        _admin(who, "add_operation", request_id, name=name, operation_id=op["operation_id"])
        return op

    @api.delete("/api/kinetic/systems/{name}/operations/{operation_id}")
    async def delete_operation(name: str, operation_id: str, who: dict = Depends(actor),
                               request_id: str = Depends(rid)):
        require_role(who, ROLE_ADMIN)
        registry.delete_operation(name, operation_id)
        _admin(who, "delete_operation", request_id, name=name, operation_id=operation_id)
        return {"deleted": True}

    # ── 액션·plan·run ──
    @api.get("/api/kinetic/actions")
    async def list_actions(request: Request, who: dict = Depends(actor)):
        return service.list_actions(who, request.query_params.get("class"))

    def _plan_args(body: dict) -> dict[str, Any]:
        if not isinstance(body.get("class"), str) or not isinstance(body.get("action"), str):
            raise KineticError("invalid_params", "class 와 action 이 필요합니다.")
        return {"class_name": body["class"], "action": body["action"], "params": body.get("params")}

    @api.post("/api/kinetic/plans")
    async def create_plan(body: dict = Body(...), who: dict = Depends(actor), request_id: str = Depends(rid)):
        return await service.plan(who, **_plan_args(body), where=body.get("where") or [], request_id=request_id)

    @api.post("/api/kinetic/plans/by-ids")
    async def create_plan_ids(body: dict = Body(...), who: dict = Depends(actor), request_id: str = Depends(rid)):
        return await service.plan(who, **_plan_args(body), ids=body.get("ids"), request_id=request_id)

    @api.get("/api/kinetic/plans/{plan_id}")
    async def get_plan(plan_id: str, _: dict = Depends(actor)):
        return service.get_plan(plan_id)

    @api.post("/api/kinetic/plans/{plan_id}/approve")
    async def approve(plan_id: str, body: dict | None = Body(default=None), who: dict = Depends(actor),
                      request_id: str = Depends(rid)):
        return await service.approve(who, plan_id, (body or {}).get("note"), request_id=request_id)

    @api.post("/api/kinetic/plans/{plan_id}/reject")
    async def reject(plan_id: str, body: dict | None = Body(default=None), who: dict = Depends(actor),
                     request_id: str = Depends(rid)):
        return await service.approve(who, plan_id, (body or {}).get("note"), request_id=request_id, reject=True)

    @api.post("/api/kinetic/plans/{plan_id}/execute")
    async def execute(plan_id: str, who: dict = Depends(actor), request_id: str = Depends(rid)):
        return await service.execute(who, plan_id, request_id=request_id)

    @api.get("/api/kinetic/runs")
    async def list_runs(limit: int = 10, who: dict = Depends(actor)):
        return service.list_runs(who, limit)

    @api.get("/api/kinetic/runs/{run_id}")
    async def get_run(run_id: str, _: dict = Depends(actor)):
        return service.get_run(run_id)

    @api.post("/api/kinetic/runs/{run_id}/retry")
    async def retry(run_id: str, who: dict = Depends(actor), request_id: str = Depends(rid)):
        return await service.retry(who, run_id, request_id=request_id)

    @api.post("/api/kinetic/runs/{run_id}/compensate")
    async def compensate(run_id: str, body: dict | None = Body(default=None), who: dict = Depends(actor),
                         request_id: str = Depends(rid)):
        return await service.compensate(who, run_id, (body or {}).get("reason"), request_id=request_id)

    @api.post("/api/kinetic/catalog/refresh")
    async def refresh(_: dict = Depends(actor)):
        try:
            return {"actions": await catalog.refresh()}
        except Exception as exc:
            raise KineticError("bad_gateway", f"그래프에서 카탈로그를 읽지 못했습니다: {exc}") from exc

    @api.get("/api/kinetic/audit")
    async def audit_log(request: Request, who: dict = Depends(actor)):
        if not {ROLE_ADMIN, ROLE_APPROVER} & set(who["roles"]):
            raise KineticError("forbidden", "감사 로그는 승인자·관리자만 볼 수 있습니다.")
        return store.list_audit(request.query_params.get("plan_id"))

    root = _Root(api, mcp, verifier, settings)
    root.state = api.state  # 테스트 편의
    return root


def _default_app():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)  # 발행 전 라벨 미존재 경고 등
    return create_app()


def run() -> None:
    import uvicorn

    s = Settings.from_env()
    uvicorn.run("app.main:_default_app", factory=True, host="0.0.0.0", port=s.port)


if __name__ == "__main__":
    run()
