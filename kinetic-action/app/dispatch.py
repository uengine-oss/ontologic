"""대상별 마이크로서비스 호출. 계약 §3 규칙 · §5 호출 경로.

- 기본: `KINETIC_SVC_BASE/<system><path>` (api-gateway 경유). `KINETIC_SVC_DIRECT=1` 이면 base_url 직접.
- 헤더: `Idempotency-Key` (전진 `<plan>:<대상>:<단계>:a<시도>`, 보상 `…:a<시도>:c`), `X-Kinetic-Run`,
  `X-Kinetic-Internal`. 키는 호출자(plans)가 정한다.
- 한 번의 execute/retry 에서 대상·단계당 한 번만 시도한다. 재시도 정책은 게이트웨이와 retry 엔드포인트 몫.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from .config import Settings
from .store import now_iso
from .sysauth import AuthUnavailable, SystemAuth
from .telemetry import span

SECRET_HEADERS = {"x-kinetic-internal", "authorization", "x-api-key"}


class Dispatcher:
    def __init__(self, settings: Settings, http: httpx.AsyncClient):
        self.settings = settings
        self.http = http
        self.sem = asyncio.Semaphore(max(1, settings.concurrency))
        self.auth = SystemAuth(http)

    def base(self, system: dict) -> str:
        if self.settings.svc_direct:
            return system["base_url"].rstrip("/")
        return f"{self.settings.svc_base}/{system['name']}"

    def url(self, system: dict, call: dict, extra_query: dict | None = None) -> str:
        url = httpx.URL(self.base(system) + call["path"])
        query = {**(call.get("query") or {}), **(extra_query or {})}
        return str(url.copy_merge_params(query)) if query else str(url)

    @staticmethod
    def idem_key(plan_id: str, target_key: str, step: str, attempt: int, compensation: bool = False) -> str:
        return f"{plan_id}:{target_key}:{step}:a{attempt}" + (":c" if compensation else "")

    @staticmethod
    def kinetic_headers(idem_key: str, run_id: str | None) -> dict:
        h = {"Idempotency-Key": idem_key}
        if run_id:
            h["X-Kinetic-Run"] = run_id
        return h

    def preview(self, system: dict, call: dict, target_key: str, step: str, idem_key: str) -> dict:
        """Plan.preview 의 Call (대상 × 단계) — 비밀 헤더 제외."""
        headers = {**call["headers"], **self.kinetic_headers(idem_key, None)}
        return {"target_key": target_key, "step": step, "method": call["method"], "url": self.url(system, call),
                "headers": {k: v for k, v in headers.items() if k.lower() not in SECRET_HEADERS},
                "body": call["body"]}

    async def _secret(self, system: dict) -> tuple[dict, dict]:
        """(비밀 헤더, 비밀 쿼리). 게이트웨이 모드에서는 게이트웨이가 시스템 인증을 주입한다 (§5·§8)."""
        h = {}
        if self.settings.internal_secret:
            h["X-Kinetic-Internal"] = self.settings.internal_secret
        if not self.settings.svc_direct:
            return h, {}
        auth_h, auth_q = await self.auth.apply(system)
        return {**h, **auth_h}, auth_q

    async def _exchange(self, system: dict, method: str, call: dict, headers: dict, body: Any,
                        timeout: float) -> httpx.Response:
        """한 번 호출. 직접 모드 login_token 이 401 을 받으면 토큰을 버리고 한 번 재로그인·재시도한다
        (게이트웨이 모드에서는 게이트웨이가 같은 일을 한다 — 계약 §9.1). AuthUnavailable·httpx.HTTPError 는 호출자가 처리."""
        for attempt in (1, 2):
            secret_h, secret_q = await self._secret(system)
            r = await self.http.request(method, self.url(system, call, secret_q), headers={**headers, **secret_h},
                                        json=body, timeout=timeout)
            if (r.status_code == 401 and attempt == 1 and self.settings.svc_direct
                    and (system.get("auth_kind") or "none") == "login_token"):
                self.auth.invalidate(system, secret_h)
                continue
            return r
        return r  # pragma: no cover

    async def health(self, system: dict) -> dict:
        """`health_path` GET (게이트웨이 경유 또는 직접), 3초 제한."""
        t0 = time.perf_counter()
        try:
            r = await self._exchange(system, "GET", {"path": system.get("health_path") or "/health"}, {}, None, 3)
            status, error = r.status_code, None if r.status_code < 300 else f"HTTP {r.status_code}"
        except httpx.HTTPError as exc:
            status, error = None, f"{type(exc).__name__}: {exc}"
        except AuthUnavailable as exc:
            status, error = None, f"auth_unavailable: {exc}"
        out = {"ok": error is None, "http_status": status, "latency_ms": round((time.perf_counter() - t0) * 1000),
               "checked_at": now_iso()}
        return out if error is None else {**out, "error": error}

    async def send(self, system: dict, call: dict, idem_key: str, run_id: str) -> dict:
        async with self.sem:
            with span("kinetic.dispatch", system=system["name"], key=idem_key, run=run_id):
                headers = {**call["headers"], **self.kinetic_headers(idem_key, run_id)}
                try:
                    r = await self._exchange(system, call["method"], call, headers,
                                             call["body"] if call["body"] is not None else None,
                                             system.get("timeout_ms", 10000) / 1000)
                except AuthUnavailable as exc:
                    return {"ok": False, "http_status": None, "response": None, "error": f"auth_unavailable: {exc}"}
                except httpx.HTTPError as exc:
                    return {"ok": False, "http_status": None, "response": None,
                            "error": f"{type(exc).__name__}: {exc}"}
        response: Any
        try:
            response = r.json()
        except ValueError:
            response = r.text[:2000]
        ok = 200 <= r.status_code < 300
        return {"ok": ok, "http_status": r.status_code, "response": response,
                "error": None if ok else f"HTTP {r.status_code}"}

    async def query(self, system: dict, path: str, query: dict) -> dict:
        """조회 경로 (계약 §9.2) — GET 한 번. → {ok, http_status, data, latency_ms, error?}. data 는 JSON(아니면 문자열)."""
        t0 = time.perf_counter()
        async with self.sem:
            with span("kinetic.query", system=system["name"], path=path):
                try:
                    r = await self._exchange(system, "GET", {"path": path, "query": query},
                                             {"Accept": "application/json"}, None,
                                             system.get("timeout_ms", 10000) / 1000)
                except AuthUnavailable as exc:
                    error = f"auth_unavailable: {exc}"
                    r = None
                except httpx.HTTPError as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    r = None
        latency = round((time.perf_counter() - t0) * 1000)
        if r is None:
            return {"ok": False, "http_status": None, "data": None, "latency_ms": latency, "error": error}
        data: Any
        try:
            data = r.json()
        except ValueError:
            data = r.text
        ok = 200 <= r.status_code < 300
        out = {"ok": ok, "http_status": r.status_code, "data": data, "latency_ms": latency}
        return out if ok else {**out, "error": f"HTTP {r.status_code}"}
