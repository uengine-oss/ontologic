"""남향 시스템 인증 (직접 모드 `KINETIC_SVC_DIRECT=1` 전용 — 게이트웨이 모드에서는 api-gateway 가 같은 일을 한다). 계약 §8.

- api_key: `header` 또는 `query_param` 에 env 값
- basic: `Authorization: Basic base64(env 값 "user:password")`
- bearer: `Authorization: Bearer <env 값>` (값에 접두가 있으면 그대로)
- oauth2_client_credentials: `token_url` 에 form POST(grant_type=client_credentials, client_id, client_secret, scope)
  → `access_token` 을 만료 60초 전까지 캐시, `Authorization: Bearer` 주입
- login_token (계약 §9.1): `token_url` 에 JSON POST(`login_body` + username/password env 값) → 응답의 `token_path`
  토큰을 (JWT `exp` 또는 `ttl_seconds`) 만료 60초 전까지 캐시, `header: <scheme> <token>` 주입.
  하위 호출이 401 이면 dispatch 가 `invalidate` 후 한 번 재로그인·재시도한다. 로그인 실패 → AuthUnavailable

비밀 값은 로그·응답에 남기지 않는다. env 가 비어 있으면 인증 없이 보낸다(서비스가 401 을 줄 것).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time

import httpx

log = logging.getLogger("kinetic.sysauth")
REFRESH_SKEW = 60  # 초 — 만료 이만큼 전에 새로 받는다


class AuthUnavailable(Exception):
    """토큰 발급 실패 (게이트웨이의 503 auth_unavailable 과 같은 의미)."""


def required_envs(system: dict) -> list[str]:
    """이 시스템 인증에 필요한 환경변수 이름 (값은 보지 않는다)."""
    kind = system.get("auth_kind") or "none"
    if kind in ("api_key", "bearer", "basic"):
        return [system["auth_secret_env"]] if system.get("auth_secret_env") else []
    if kind == "oauth2_client_credentials":
        return [system["auth_client_secret_env"]] if system.get("auth_client_secret_env") else []
    if kind == "login_token":
        cfg = _login_cfg(system)
        return [e for e in (cfg.get("username_env"), cfg.get("password_env")) if e]
    return []


def _login_cfg(system: dict) -> dict:
    try:
        cfg = json.loads(system.get("auth_login") or "{}")
    except ValueError:
        cfg = {}
    return cfg if isinstance(cfg, dict) else {}


def jwt_exp(token: str) -> float | None:
    """JWT 페이로드의 `exp` (검증하지 않는다 — 만료 시각만 본다). JWT 가 아니면 None."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        raw = parts[1] + "=" * (-len(parts[1]) % 4)
        exp = json.loads(base64.urlsafe_b64decode(raw.encode()).decode()).get("exp")
        return float(exp) if isinstance(exp, (int, float)) and not isinstance(exp, bool) else None
    except Exception:
        return None


def dig(value, path: str):
    for p in path.split("."):
        if isinstance(value, dict) and p in value:
            value = value[p]
        elif isinstance(value, list) and p.isdigit() and int(p) < len(value):
            value = value[int(p)]
        else:
            return None
    return value


class SystemAuth:
    def __init__(self, http: httpx.AsyncClient, env=None):
        self.http = http
        self.env = env or os.environ.get
        self._tokens: dict[tuple, tuple[str, float]] = {}
        self._locks: dict[tuple, asyncio.Lock] = {}
        self.token_requests = 0  # 테스트·관찰용

    async def apply(self, system: dict) -> tuple[dict, dict]:
        """(헤더, 쿼리 파라미터)."""
        kind = system.get("auth_kind") or "none"
        if kind == "none":
            return {}, {}
        if kind == "oauth2_client_credentials":
            return {"Authorization": f"Bearer {await self.token(system)}"}, {}
        if kind == "login_token":
            token = await self.login_token(system)
            return {system.get("auth_header") or "Authorization": self._login_value(system, token)}, {}
        value = self.env(system.get("auth_secret_env") or "", "") if system.get("auth_secret_env") else ""
        if not value:
            return {}, {}
        if kind == "api_key":
            if system.get("auth_query_param"):
                return {}, {system["auth_query_param"]: value}
            return {system.get("auth_header") or "X-API-Key": value}, {}
        if kind == "basic":
            return {"Authorization": "Basic " + base64.b64encode(value.encode()).decode()}, {}
        if kind == "bearer":
            if not value.lower().startswith("bearer "):
                value = f"Bearer {value}"
            return {system.get("auth_header") or "Authorization": value}, {}
        return {}, {}

    async def token(self, system: dict) -> str:
        raw = system.get("auth_scopes") or []
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                raw = raw.split()
        scopes = tuple(raw or ())
        key = (system.get("auth_token_url"), system.get("auth_client_id"), scopes)
        cached = self._tokens.get(key)
        if cached and cached[1] > time.time():
            return cached[0]
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._tokens.get(key)
            if cached and cached[1] > time.time():
                return cached[0]
            secret = self.env(system.get("auth_client_secret_env") or "", "") or ""
            form = {"grant_type": "client_credentials", "client_id": system.get("auth_client_id") or "",
                    "client_secret": secret}
            if scopes:
                form["scope"] = " ".join(scopes)
            self.token_requests += 1
            try:
                r = await self.http.post(system["auth_token_url"], data=form, timeout=10,
                                         headers={"Accept": "application/json"})
                r.raise_for_status()
                body = r.json()
                token = body["access_token"]
            except Exception as exc:  # 비밀이 섞일 수 있는 응답 본문은 남기지 않는다
                status = getattr(getattr(exc, "response", None), "status_code", None)
                log.warning("oauth2 token request to %s failed (%s%s)", system.get("auth_token_url"),
                            type(exc).__name__, f" HTTP {status}" if status else "")
                raise AuthUnavailable(f"토큰 발급 실패: {type(exc).__name__}"
                                      + (f" HTTP {status}" if status else "")) from None
            expires_in = body.get("expires_in")
            try:
                ttl = float(expires_in) if expires_in is not None else 300.0
            except (TypeError, ValueError):
                ttl = 300.0
            self._tokens[key] = (token, time.time() + max(0.0, ttl - REFRESH_SKEW))
            return token

    # ── login_token (계약 §9.1) ──
    @staticmethod
    def _login_key(system: dict) -> tuple:
        cfg = _login_cfg(system)
        return ("login", system.get("auth_token_url"), cfg.get("username_env"),
                json.dumps(cfg.get("login_body") or {}, sort_keys=True))

    @staticmethod
    def _login_value(system: dict, token: str) -> str:
        scheme = _login_cfg(system).get("scheme", "Bearer")
        return f"{scheme} {token}" if scheme else token

    def invalidate(self, system: dict, used_headers: dict) -> None:
        """하위 서비스 401 → 그 토큰을 버린다 (다른 요청이 이미 새로 받았으면 그대로 둔다)."""
        if (system.get("auth_kind") or "none") != "login_token":
            return
        key = self._login_key(system)
        cached = self._tokens.get(key)
        used = used_headers.get(system.get("auth_header") or "Authorization")
        if cached and used == self._login_value(system, cached[0]):
            self._tokens.pop(key, None)

    async def login_token(self, system: dict) -> str:
        key = self._login_key(system)
        cached = self._tokens.get(key)
        if cached and cached[1] > time.time():
            return cached[0]
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._tokens.get(key)
            if cached and cached[1] > time.time():
                return cached[0]
            cfg = _login_cfg(system)
            url = system.get("auth_token_url")
            user = self.env(cfg.get("username_env") or "", "") if cfg.get("username_env") else ""
            password = self.env(cfg.get("password_env") or "", "") if cfg.get("password_env") else ""
            missing = [e for e, v in ((cfg.get("username_env"), user), (cfg.get("password_env"), password)) if not v]
            if missing:
                log.warning("login_token: env %s not set (token_url %s)", missing, url)
                raise AuthUnavailable(f"로그인 env 없음: {', '.join(str(m) for m in missing)}")
            body = {**(cfg.get("login_body") or {}), cfg.get("username_field") or "loginId": user,
                    cfg.get("password_field") or "password": password}
            self.token_requests += 1
            try:
                r = await self.http.post(url, json=body, timeout=10, headers={"Accept": "application/json"})
                r.raise_for_status()
                token = dig(r.json(), cfg.get("token_path") or "token")
                if not isinstance(token, str) or not token:
                    raise ValueError("no token")
            except Exception as exc:  # 응답 본문·비밀은 남기지 않는다
                status = getattr(getattr(exc, "response", None), "status_code", None)
                why = f"HTTP {status}" if status else ("응답에 토큰 없음" if isinstance(exc, ValueError)
                                                      else type(exc).__name__)
                log.warning("login_token: login to %s failed (%s)", url, why)
                raise AuthUnavailable(f"로그인 실패: {why}") from None
            exp = jwt_exp(token)
            try:
                ttl = float(cfg.get("ttl_seconds") or 1800)
            except (TypeError, ValueError):
                ttl = 1800.0
            expires = exp if exp is not None else time.time() + ttl
            self._tokens[key] = (token, expires - REFRESH_SKEW)
            return token
