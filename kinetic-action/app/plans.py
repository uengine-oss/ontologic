"""plan → (승인) → execute → retry. 키네틱 액션의 핵심 흐름 (계약 §3 규칙).

- plan 은 dry-run 이다: 대상 조회 · 인스턴스별 정책 판정 · 호출 미리보기만 하고 아무것도 바꾸지 않는다.
- 허용 대상 수 > confirm_threshold 면 사람 승인(REST 만) 이 있어야 실행된다.
- 실행 직전 대상을 다시 조회하고 정책을 다시 평가한다. 그 사이 정책을 잃은 대상은 `skipped`.
- 같은 plan 재실행은 기존 run 을 그대로 돌려준다 (plan 당 run 하나 — DB unique 로 보장).
- 대상 하나 = 사가 하나 (계약 §1.3). 단계는 순서대로, 대상끼리는 병렬. i 번째 단계가 실패하면
  성공한 단계를 역순으로 자동 보상한다(`compensated`, 보상도 실패하면 `dead`).
- 취소(`compensate`)는 성공한 대상을 실행 완료 역순(`finished_seq` 내림차순)으로 하나씩, 단계 역순으로 보상한다.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from . import policy
from .auth import ROLE_APPROVER, require_role
from .catalog import Action, Catalog, Step
from .config import Settings
from .dispatch import Dispatcher
from .errors import KineticError
from .graph import GraphReader
from .mapping import build_call, validate_params
from .registry import Registry
from .store import Store, now_iso, now_ms
from .targeting import validate_filters
from .telemetry import span

LIVE = ("planned", "awaiting_approval", "approved")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _public(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if not k.startswith("_")}


def _run_status(targets: list[dict]) -> str:
    ok = sum(t["status"] == "succeeded" for t in targets)
    bad = sum(t["status"] in ("failed", "dead", "compensated") for t in targets)
    if ok and not bad:
        return "succeeded"
    if ok and bad:
        return "partial"
    return "failed"  # 실패만 있거나 전부 skipped (실제로 바뀐 것이 없음)


PAGED_KEYS = ("items", "content", "data", "results", "records", "rows", "list", "value")


def _qv(v: Any) -> Any:
    return str(v).lower() if isinstance(v, bool) else v


def fill_path(template: str, values: dict) -> str:
    """`{변수}` 를 path_params 로 채운다 (URL 인코딩). 빠진 변수는 invalid_params."""
    def sub(m):
        v = values.get(m.group(1))
        if v is None or v == "":
            raise KineticError("invalid_params", f"경로 변수 '{m.group(1)}' 값(path_params)이 없습니다.")
        return quote(str(v), safe="")
    return re.sub(r"\{([^}]+)\}", sub, template)


def truncate(data: Any, limit: int, depth: int = 0) -> tuple[Any, bool]:
    """배열(최상위 또는 흔한 페이지 모양 `{items|content|data|results|records|rows|list|value: [...]}`, 2단계까지)을
    `limit` 개로 자른다. → (data, truncated)."""
    if isinstance(data, list):
        return (data[:limit], True) if len(data) > limit else (data, False)
    if isinstance(data, dict) and depth < 2:
        out = dict(data)
        cut = False
        for k in PAGED_KEYS:
            if isinstance(data.get(k), (list, dict)):
                out[k], c = truncate(data[k], limit, depth + 1)
                cut = cut or c
        return (out, True) if cut else (data, False)
    return data, False


class KineticService:
    def __init__(self, settings: Settings, store: Store, catalog: Catalog, registry: Registry,
                 dispatcher: Dispatcher, graph: GraphReader):
        self.settings = settings
        self.store = store
        self.catalog = catalog
        self.registry = registry
        self.dispatcher = dispatcher
        self.graph = graph
        self._locks: dict[str, asyncio.Lock] = {}

    # ── 조회 경로 (계약 §9.2) ──
    async def query(self, actor: dict, system_name: str, operation_id: Any, path_params: Any = None,
                    query: Any = None, *, request_id: str | None = None) -> dict:
        """등록된 시스템의 GET operation 을 바로 부른다 (계획·승인 없음). 쓰기는 오직 액션."""
        if not isinstance(operation_id, str) or not operation_id:
            raise KineticError("invalid_params", "operation_id 가 필요합니다.")
        for name, value in (("path_params", path_params), ("query", query)):
            if value is not None and not isinstance(value, dict):
                raise KineticError("invalid_params", f"{name} 는 객체여야 합니다.")
        system = self.registry.system(system_name)
        self.registry.require_executable(system_name)
        op = self.registry.operation(system_name, operation_id)
        if str(op.get("method") or "").upper() != "GET":
            raise KineticError("not_readonly", f"'{operation_id}' 는 {op.get('method')} operation 입니다 — 조회는 GET 만, "
                                               "쓰기는 액션(plan → execute)으로 하세요.")
        path = fill_path(op["path"], path_params or {})
        q = {}
        for k, v in (query or {}).items():
            if v is None:
                continue
            if isinstance(v, (dict,)) or (isinstance(v, list) and any(isinstance(x, (dict, list)) for x in v)):
                raise KineticError("invalid_params", f"query.{k} 는 스칼라 또는 스칼라 배열이어야 합니다.")
            q[str(k)] = [_qv(x) for x in v] if isinstance(v, list) else _qv(v)
        out = await self.dispatcher.query(system, path, q)
        out["data"], out["truncated"] = truncate(out["data"], self.settings.query_max_items)
        self.store.audit("query", actor_sub=actor["sub"], request_id=request_id,
                         detail={"system": system_name, "operation_id": operation_id, "http_status": out["http_status"],
                                 "ok": out["ok"], "truncated": out["truncated"]})
        return out

    # ── 카탈로그 ──
    def list_actions(self, actor: dict, class_name: str | None = None) -> list[dict]:
        return [a.summary() for (c, _), a in sorted(self.catalog.actions.items())
                if (not class_name or c == class_name) and policy.visible(a.policy, actor)]

    def actions_using(self, system: str) -> list[str]:
        return [f"{c}.{n}" for (c, n), a in sorted(self.catalog.actions.items()) if system in a.systems]

    def _action(self, actor: dict, class_name: str, action: str) -> Action:
        a = self.catalog.get(class_name, action)
        if a is None:
            raise KineticError("not_found", f"액션 '{class_name}.{action}' 이 발행되지 않았습니다.")
        if not policy.visible(a.policy, actor):
            raise KineticError("forbidden", f"액션 '{class_name}.{action}' 을 쓸 권한이 없습니다.")
        return a

    def _key(self, a: Action, eid: str, props: dict) -> str:
        v = props.get(a.key_property) if a.key_property else None
        return str(v) if v is not None else eid

    def _ctx(self, key: str, props: dict, actor: dict, params: dict, plan_id: str, run_id: str | None, **extra):
        return {"this": props, "key": key, "params": params, "actor": actor, "plan_id": plan_id, "run_id": run_id,
                "before": props, "steps": {}, **extra}

    def _check_ops(self, a: Action) -> None:
        """단계·보상의 시스템/operation 이 모두 등록돼 있어야 한다 (없으면 not_found)."""
        for s in a.steps:  # 어댑터가 필요한 시스템(soap·grpc…)은 실행 불가 — not_executable(422)
            self.registry.require_executable(s.system)
            if s.compensation:
                self.registry.require_executable(s.compensation["system"])
        for s in a.steps:
            self.registry.operation(s.system, s.operation_id)
            if s.compensation:
                self.registry.operation(s.compensation["system"], s.compensation["operation_id"])

    # ── plan ──
    async def plan(self, actor: dict, class_name: str, action: str, *, where: Any = None,
                   ids: list | None = None, params: Any = None, request_id: str | None = None) -> dict:
        a = self._action(actor, class_name, action)
        params = validate_params(a.parameters or {}, params)
        filters = validate_filters(where) if ids is None else []
        if ids is not None and (not isinstance(ids, list) or not ids):
            raise KineticError("invalid_filter", "ids 는 비어 있지 않은 배열이어야 합니다.")
        self._check_ops(a)
        with span("kinetic.plan", cls=class_name, action=action, actor=actor.get("sub")):
            rows = await self.graph.find(class_name, filters, a.max_targets + 1, classes=self.catalog.classes,
                                         key_property=a.key_property or None,
                                         ids=[str(i) for i in ids] if ids is not None else None)
        if len(rows) > a.max_targets:
            raise KineticError("too_many_targets", f"대상이 max_targets({a.max_targets}) 를 넘습니다. 조건을 좁히세요.")
        plan_id, now = _new_id("pln"), now_iso()
        allowed, denied, preview = [], [], []
        for eid, props in rows:
            key = self._key(a, eid, props)
            ok, reason = policy.evaluate(a.policy, actor, {**props, "$key": key}, params, now)
            if not ok:
                denied.append({"key": key, "props": props, "reason": reason})
                continue
            allowed.append({"key": key, "props": props})
            ctx = self._ctx(key, props, actor, params, plan_id, None, preview=True)
            for st in a.steps:  # 대상 × 단계. 보상은 미리보지 않고 compensable 만 표시
                call = build_call(self.registry.operation(st.system, st.operation_id), st.arg_mapping, ctx)
                preview.append({**self.dispatcher.preview(self.registry.system(st.system), call, key, st.name,
                                                          self.dispatcher.idem_key(plan_id, key, st.name, 1)),
                                "compensable": st.compensation is not None})
        requires = len(allowed) > a.confirm_threshold
        plan = {
            "id": plan_id, "class": class_name, "action": action, "actor_sub": actor["sub"], "params": params,
            "where": filters if ids is None else [{"prop": a.key_property or "$elementId", "op": "in", "value": ids}],
            "status": "awaiting_approval" if requires else "planned", "requires_approval": requires,
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=self.settings.plan_ttl))
            .isoformat(timespec="seconds").replace("+00:00", "Z"),
            "allowed": allowed, "denied": denied, "preview": preview, "created_at": now,
            "approved_by": None, "approved_at": None, "approval_note": None, "run_id": None,
        }
        self.store.save_plan(plan, new=True)
        self.store.audit("plan", actor_sub=actor["sub"], request_id=request_id, plan_id=plan_id,
                         detail={"class": class_name, "action": action, "allowed": len(allowed),
                                 "denied": len(denied), "requires_approval": requires})
        return _public(plan)

    def _load(self, plan_id: str) -> dict:
        plan = self.store.get_plan(plan_id)
        if plan is None:
            raise KineticError("not_found", f"plan '{plan_id}' 이 없습니다.")
        if plan["status"] in LIVE and datetime.fromisoformat(plan["expires_at"]) < datetime.now(timezone.utc):
            plan["status"] = "expired"
            self.store.save_plan(plan)
            self.store.audit("expire", actor_sub=None, request_id=None, plan_id=plan_id)
        return plan

    def get_plan(self, plan_id: str) -> dict:
        return _public(self._load(plan_id))

    async def approve(self, actor: dict, plan_id: str, note: str | None = None, *, request_id=None,
                      reject: bool = False) -> dict:
        require_role(actor, ROLE_APPROVER)
        async with self._lock(plan_id):
            plan = self._load(plan_id)
            if plan["status"] == "expired":
                raise KineticError("plan_expired", "plan 이 만료됐습니다. 다시 plan 하세요.")
            if plan["status"] not in ("planned", "awaiting_approval"):
                raise KineticError("conflict", f"상태가 '{plan['status']}' 인 plan 은 승인/반려할 수 없습니다.")
            plan.update(status="rejected" if reject else "approved", approved_by=actor["sub"],
                        approved_at=now_iso(), approval_note=note)
            self.store.save_plan(plan)
            self.store.audit("reject" if reject else "approve", actor_sub=actor["sub"], request_id=request_id,
                             plan_id=plan_id, detail={"note": note})
            return _public(plan)

    def _lock(self, plan_id: str) -> asyncio.Lock:
        return self._locks.setdefault(plan_id, asyncio.Lock())

    # ── execute ──
    async def execute(self, actor: dict, plan_id: str, *, request_id: str | None = None) -> dict:
        plan = self._load(plan_id)
        if plan["actor_sub"] != actor.get("sub"):
            raise KineticError("not_plan_owner", "plan 작성자만 실행할 수 있습니다.")
        async with self._lock(plan_id):
            existing = self.store.get_run_by_plan(plan_id)
            if existing:
                return existing
            plan = self._load(plan_id)
            if plan["status"] == "expired":
                raise KineticError("plan_expired", "plan 이 만료됐습니다. 다시 plan 하세요.")
            if plan["status"] == "rejected":
                raise KineticError("forbidden", "반려된 plan 입니다.")
            if plan["requires_approval"] and plan["status"] != "approved":
                raise KineticError("approval_required",
                                   f"허용 대상 {len(plan['allowed'])}건 — 사람 승인이 필요합니다 (Studio 에서 승인).")
            if not plan["allowed"]:
                # 허용 대상이 없는 plan 은 실행하지 않는다 — 빈 run 이 「실패」로 남아 사람을 헷갈리게 한다(실측)
                raise KineticError("nothing_to_execute",
                                   "허용된 대상이 0건입니다. 대상 지정(키 속성 값)이나 조건을 고쳐 다시 plan 하세요.")
            a = self._action(actor, plan["class"], plan["action"])
            self._check_ops(a)
            run_id, now = _new_id("run"), now_iso()
            keys = [t["key"] for t in plan["allowed"]]
            current: dict[str, dict] = {}
            if keys:
                rows = await self.graph.find(plan["class"], [], len(keys) + 1, classes=self.catalog.classes,
                                             key_property=a.key_property or None, ids=keys)
                current = {self._key(a, eid, props): props for eid, props in rows}
            targets, todo = [], []
            for key in keys:
                t = {"key": key, "status": "pending", "http_status": None, "response": None, "error": None,
                     "attempts": 0, "finished_seq": None, "before": None, "compensated_by": None,
                     "steps": [_step_rec(st) for st in a.steps]}
                props = current.get(key)
                if props is None:
                    t.update(status="skipped", error="대상이 더 이상 존재하지 않습니다")
                else:
                    ok, reason = policy.evaluate(a.policy, actor, {**props, "$key": key}, plan["params"], now)
                    if not ok:
                        t.update(status="skipped", error=f"재평가 거부: {reason}")
                    else:
                        t["before"] = props  # $before — 보상에서 원래 값 복원에 쓴다
                        todo.append(t)
                if t["status"] == "skipped":
                    for rec in t["steps"]:
                        rec["status"] = "skipped"
                targets.append(t)
            run = {"id": run_id, "plan_id": plan_id, "status": "running", "targets": targets,
                   "started_at": now, "finished_at": None, "compensations": [], "cancel": None}
            if not self.store.create_run(run, {}):  # 다른 프로세스가 먼저 실행
                return self.store.get_run_by_plan(plan_id)
            plan.update(status="executed", run_id=run_id)
            self.store.save_plan(plan)
            with span("kinetic.execute", plan=plan_id, run=run_id, targets=len(todo)):
                await self._dispatch(a, plan, run, actor, todo)
            self.store.audit("execute", actor_sub=actor["sub"], request_id=request_id, plan_id=plan_id,
                             run_id=run_id, detail={"status": run["status"], "compensations": len(run["compensations"]),
                                                    "counts": _counts(targets)})
            return run

    async def _dispatch(self, a: Action, plan: dict, run: dict, actor: dict, todo: list[dict]) -> None:
        await asyncio.gather(*(self._saga(a, plan, run, actor, t) for t in todo))
        run["status"] = _run_status(run["targets"])
        run["finished_at"] = now_iso()
        self.store.save_run(run)

    async def _call(self, system_name: str, operation_id: str, mapping: dict, ctx: dict, key: str,
                    run_id: str) -> dict:
        try:
            system = self.registry.system(system_name)
            call = build_call(self.registry.operation(system_name, operation_id), mapping, ctx)
        except KineticError as exc:  # 매핑 실패($steps 응답 없음 등)는 그 호출의 실패
            return {"ok": False, "http_status": None, "response": None, "error": exc.message}
        return await self.dispatcher.send(system, call, key, run_id)

    def _target_ctx(self, plan: dict, run: dict, actor: dict, t: dict, **extra) -> dict:
        ctx = self._ctx(t["key"], t["before"] or {}, actor, plan["params"], plan["id"], run["id"], **extra)
        ctx["steps"] = {r["name"]: r["response"] for r in t["steps"] if r["status"] == "succeeded"}
        return ctx

    async def _saga(self, a: Action, plan: dict, run: dict, actor: dict, t: dict) -> None:
        """대상 하나를 1단계부터 끝까지. 실패하면 성공한 단계를 역순 자동 보상."""
        t["attempts"] += 1
        t.update(status="running", error=None, compensated_by=None, steps=[_step_rec(st) for st in a.steps])
        failed = None
        for st, rec in zip(a.steps, t["steps"]):
            res = await self._call(st.system, st.operation_id, st.arg_mapping, self._target_ctx(plan, run, actor, t),
                                   self.dispatcher.idem_key(plan["id"], t["key"], st.name, t["attempts"]), run["id"])
            rec.update(status="succeeded" if res["ok"] else "failed", http_status=res["http_status"],
                       response=res["response"], error=res["error"])
            t.update(http_status=res["http_status"], response=res["response"])
            if not res["ok"]:
                failed = st
                t["error"] = f"{st.name}: {res['error']}"
                break
        if failed is None:
            t["status"] = "succeeded"
            await self._writeback(a, t)
        else:
            for rec in t["steps"]:
                if rec["status"] == "pending":
                    rec["status"] = "skipped"
            if any(r["status"] == "succeeded" for r in t["steps"]):
                ok = await self._undo(a, plan, run, actor, t, "auto", f"자동 보상: '{failed.name}' 단계 실패")
                t.update(status="compensated" if ok else "dead", compensated_by="auto")
            else:
                t["status"] = "failed"
            if t["status"] != "dead" and t["attempts"] >= self.settings.max_attempts:
                t["status"] = "dead"
        t["finished_seq"] = max((x["finished_seq"] or 0) for x in run["targets"]) + 1

    async def _undo(self, a: Action, plan: dict, run: dict, actor: dict, t: dict, trigger: str, reason: str) -> bool:
        """성공한 단계를 역순으로 보상. 보상 정의가 없는 단계는 `none`. 하나라도 실패하면 False (나머지는 계속)."""
        steps = {st.name: st for st in a.steps}
        ctx = self._target_ctx(plan, run, actor, t, cancel={"reason": reason})
        ok = True
        for rec in reversed(t["steps"]):
            if rec["status"] != "succeeded" or rec.get("compensation"):
                continue
            st: Step | None = steps.get(rec["name"])
            if st is None or st.compensation is None:
                rec["compensation"] = {"status": "none", "http_status": None, "response": None, "at": now_ms(),
                                       **({"error": "단계 정의가 사라졌습니다"} if st is None else {})}
                ok = ok and st is not None
                continue
            c = st.compensation
            res = await self._call(c["system"], c["operation_id"], c["arg_mapping"], ctx,
                                   self.dispatcher.idem_key(plan["id"], t["key"], st.name, t["attempts"], True),
                                   run["id"])
            at = now_ms()
            rec["compensation"] = {"status": "succeeded" if res["ok"] else "failed", "http_status": res["http_status"],
                                   "response": res["response"], "at": at,
                                   **({} if res["ok"] else {"error": res["error"]})}
            run["compensations"].append({
                "seq": len(run["compensations"]) + 1, "at": at, "target_key": t["key"], "step": st.name,
                "system": c["system"], "operation_id": c["operation_id"],
                "status": rec["compensation"]["status"], "http_status": res["http_status"], "trigger": trigger})
            ok = ok and res["ok"]
        return ok

    async def _writeback(self, a: Action, t: dict, *, revert: bool = False) -> None:
        if not a.writeback_property:
            return
        if revert:
            value = (t.get("before") or {}).get(a.writeback_property)
        else:  # 첫 단계 응답의 status (없으면 "done")
            resp = t["steps"][0]["response"] if t.get("steps") else t["response"]
            value = resp["status"] if isinstance(resp, dict) and resp.get("status") is not None else "done"
        try:
            await self.graph.set_property(a.class_name, a.key_property or None, t["key"], a.writeback_property, value)
        except Exception as exc:  # 호출은 성공했다 — 결과를 뒤집지 않고 기록만
            t["writeback_error"] = str(exc)[:300]

    def get_run(self, run_id: str) -> dict:
        run = self.store.get_run(run_id)
        if run is None:
            raise KineticError("not_found", f"run '{run_id}' 이 없습니다.")
        return run

    def list_runs(self, actor: dict, limit: int = 10) -> list[dict]:
        """호출자가 만든 plan 의 run — 최근 것부터. 「방금 처리한 건 모두 취소」 를 대화 기록에 기대지 않고 하려고."""
        out = []
        for run in self.store.list_runs():
            plan = self.store.get_plan(run["plan_id"]) or {}
            if plan.get("actor_sub") != actor["sub"]:
                continue
            out.append({"run_id": run["id"], "plan_id": run["plan_id"], "class": plan.get("class"),
                        "action": plan.get("action"), "status": run["status"], "started_at": run.get("started_at"),
                        "targets": [t["key"] for t in run.get("targets", [])],
                        "cancellable": run["status"] in ("succeeded", "partial")})
        out.reverse()  # 같은 시각이면 나중에 저장된 run 이 앞 (정렬은 안정적)
        out.sort(key=lambda r: r.get("started_at") or "", reverse=True)
        return out[: max(1, min(int(limit), 50))]

    async def retry(self, actor: dict, run_id: str, *, request_id: str | None = None) -> dict:
        """실패·자동보상된 대상을 1단계부터 새 시도 번호(`:a<n>`)로 다시. 정책은 재평가하지 않는다."""
        run = self.get_run(run_id)
        plan = self._load(run["plan_id"])
        if plan["actor_sub"] != actor.get("sub"):
            raise KineticError("not_plan_owner", "plan 작성자만 재시도할 수 있습니다.")
        async with self._lock(plan["id"]):
            run = self.get_run(run_id)
            if run.get("cancel"):
                raise KineticError("conflict", "취소된 run 은 재시도할 수 없습니다.")
            a = self._action(actor, plan["class"], plan["action"])
            self._check_ops(a)
            todo = [t for t in run["targets"] if "steps" in t and (
                t["status"] == "failed" or (t["status"] == "compensated" and t.get("compensated_by") == "auto"))]
            for t in [t for t in todo if t["attempts"] >= self.settings.max_attempts]:
                t["status"] = "dead"
            todo = [t for t in todo if t["status"] != "dead"]
            await self._dispatch(a, plan, run, actor, todo)
            self.store.audit("retry", actor_sub=actor["sub"], request_id=request_id, plan_id=plan["id"],
                             run_id=run_id, detail={"retried": [t["key"] for t in todo], "status": run["status"]})
            return run

    async def compensate(self, actor: dict, run_id: str, reason: str | None = None, *,
                         request_id: str | None = None) -> dict:
        """취소 — 성공한 대상을 실행 완료 역순으로 하나씩, 단계 역순으로 보상. 승인 불필요(원상 복구 방향).
        plan 작성자 또는 approver. 같은 run 재취소는 기존 결과."""
        run = self.get_run(run_id)
        plan = self._load(run["plan_id"])
        if plan["actor_sub"] != actor.get("sub") and ROLE_APPROVER not in actor.get("roles", []):
            raise KineticError("not_plan_owner", "plan 작성자 또는 승인자만 취소할 수 있습니다.")
        async with self._lock(plan["id"]):
            run = self.get_run(run_id)
            if run.get("cancel"):
                return run
            if any("steps" not in t for t in run["targets"]):
                raise KineticError("conflict", "단계 기록이 없는 (이전 형식) run 은 취소할 수 없습니다.")
            a = self.catalog.get(plan["class"], plan["action"])
            if a is None:
                raise KineticError("not_found", f"액션 '{plan['class']}.{plan['action']}' 이 발행되지 않았습니다.")
            reason = (reason or "").strip() or "사용자 취소"
            run["cancel"] = {"actor_sub": actor["sub"], "reason": reason, "at": now_ms()}
            run.setdefault("compensations", [])
            todo = sorted((t for t in run["targets"] if t["status"] == "succeeded"),
                          key=lambda t: t["finished_seq"] or 0, reverse=True)
            with span("kinetic.compensate", plan=plan["id"], run=run_id, targets=len(todo)):
                for t in todo:  # 하나씩 — 순서가 곧 의미
                    ok = await self._undo(a, plan, run, actor, t, "cancel", reason)
                    t.update(status="compensated" if ok else "dead", compensated_by="cancel")
                    if ok:
                        await self._writeback(a, t, revert=True)
            run["status"] = "partially_compensated" if any(t["status"] == "dead" for t in run["targets"]) \
                else "compensated"
            run["finished_at"] = now_iso()
            self.store.save_run(run)
            self.store.audit("compensate", actor_sub=actor["sub"], request_id=request_id, plan_id=plan["id"],
                             run_id=run_id, detail={"reason": reason, "status": run["status"],
                                                    "targets": [t["key"] for t in todo],
                                                    "calls": sum(c["trigger"] == "cancel" for c in run["compensations"])})
            return run


def _step_rec(st: Step) -> dict:
    return {"name": st.name, "title": st.title, "system": st.system, "status": "pending", "http_status": None,
            "response": None, "error": None, "compensation": None}


def _counts(targets: list[dict]) -> dict:
    return {s: sum(t["status"] == s for t in targets) for s in {t["status"] for t in targets}}
