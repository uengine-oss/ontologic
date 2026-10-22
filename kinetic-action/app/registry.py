"""서비스 레지스트리 — 시스템 등록과 OpenAPI → Operation 해석. 계약 §3 System/Operation/Route.

비밀 값은 저장하지 않는다. `auth.secret_env` 는 **환경변수 이름**이고, 값은 호출 시점에
(직접 호출 모드) 또는 api-gateway 가(게이트웨이 모드) 그 환경변수에서 읽는다.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from .errors import KineticError
from .specs import FORMAT_PROTOCOL, SPEC_FORMATS, detect_format, load_text, swagger2_to_openapi3, wsdl_operations
from .store import Store, now_iso
from .sysauth import required_envs

SYSTEM_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
METHODS = ("get", "post", "put", "patch", "delete")
_DEFAULT_HEADER = {"api_key": "X-API-Key", "bearer": "Authorization", "basic": "Authorization",
                   "oauth2_client_credentials": "Authorization"}
AUTH_KINDS = ("none", "api_key", "basic", "bearer", "oauth2_client_credentials", "login_token")
FIELD_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$-]{0,99}$")
TOKEN_PATH_RE = re.compile(r"^[A-Za-z0-9_$-]{1,100}(\.[A-Za-z0-9_$-]{1,100}){0,9}$")
SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]{0,29})?$")
SECRET_KEYS = {"secret", "value", "password", "passwd", "pwd", "client_secret", "token", "api_key", "apikey",
               "access_token"}
LOGIN_DEFAULTS = {"username_field": "loginId", "password_field": "password", "token_path": "token",
                  "header": "Authorization", "scheme": "Bearer", "ttl_seconds": 1800}
PROTOCOLS = ("rest", "odata", "graphql", "grpc", "soap", "db_procedure", "async")
EXECUTABLE_PROTOCOLS = ("rest", "odata")  # 그 밖은 어댑터 필요 (로드맵: soap → db_procedure → grpc → graphql → async)
ENV_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,49}$")
ICON_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
PARAM_NAME_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


def _deref(node: Any, spec: dict, depth: int = 0) -> Any:
    """`#/components/...` 참조를 펼친다 (순환 방지 깊이 제한)."""
    if depth > 8:
        return node
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/"):
            target: Any = spec
            for part in ref[2:].split("/"):
                target = target.get(part, {}) if isinstance(target, dict) else {}
            return _deref(target, spec, depth + 1)
        return {k: _deref(v, spec, depth + 1) for k, v in node.items()}
    if isinstance(node, list):
        return [_deref(v, spec, depth + 1) for v in node]
    return node


def _server_prefix(spec: dict, base_url: str | None) -> str:
    """OpenAPI 3 의 경로는 `servers[0].url` 기준 상대 경로다. 그 URL 의 경로 부분(예 Swagger 2 basePath `/api/v1`)을
    base_url 이 이미 담고 있지 않으면 operation path 앞에 붙인다."""
    servers = spec.get("servers") or []
    if not servers or not isinstance(servers[0], dict) or not isinstance(servers[0].get("url"), str):
        return ""
    url = servers[0]["url"]
    if "{" in url:  # 서버 변수는 해석하지 않는다
        return ""
    path = urlsplit(url).path if "://" in url else url
    path = "/" + path.strip("/") if path.strip("/") else ""
    if not path or (base_url and urlsplit(base_url).path.rstrip("/").endswith(path)):
        return ""
    return path


def parse_openapi(spec: dict, base_url: str | None = None) -> list[dict]:
    ops = []
    prefix = _server_prefix(spec, base_url)
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        common = item.get("parameters") or []
        for method in METHODS:
            op = item.get(method)
            if not isinstance(op, dict) or not op.get("operationId"):
                continue
            params = []
            for p in [*common, *(op.get("parameters") or [])]:
                p = _deref(p, spec)
                params.append({"name": p.get("name"), "in": p.get("in"),
                               "required": bool(p.get("required")), "schema": p.get("schema") or {}})
            body = ((op.get("requestBody") or {}).get("content") or {}).get("application/json") or {}
            ops.append({
                "operation_id": op["operationId"], "method": method.upper(), "path": prefix + path,
                "summary": op.get("summary") or "", "parameters": params,
                "request_body_schema": _deref(body.get("schema"), spec) if body else None,
            })
    return ops


OP_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,99}$")
PARAM_IN = ("path", "query", "header")
RESERVED = {"routes"}  # GET /systems/routes 와 겹치는 이름


def _manual(row: dict) -> list[dict]:
    return json.loads(row.get("manual_ops") or "[]")


def _jlist(value: Any) -> list:
    try:
        out = json.loads(value) if isinstance(value, str) else value
    except ValueError:
        return []
    return out if isinstance(out, list) else []


def protocol_of(row: dict) -> str:
    return row.get("protocol") or "rest"


def is_executable(row: dict) -> bool:
    return protocol_of(row) in EXECUTABLE_PROTOCOLS


def spec_operations(row: dict) -> list[dict]:
    """저장된 스펙에서 뽑은 operation (출처 표시는 merged_operations 가 붙인다)."""
    if row.get("spec_format") == "wsdl":
        return wsdl_operations(row.get("spec_text") or "")
    return parse_openapi(json.loads(row.get("openapi") or "{}"), row.get("base_url"))


def merged_operations(row: dict) -> dict[str, dict]:
    """스펙 operation + 수동 등록분 (같은 operationId 는 수동이 이긴다)."""
    src = "wsdl" if row.get("spec_format") == "wsdl" else "openapi"
    ops = {o["operation_id"]: {**o, "source": src} for o in spec_operations(row)}
    ops.update({o["operation_id"]: {**o, "source": "manual"} for o in _manual(row)})
    return ops


def environments_of(row: dict) -> list[dict]:
    envs = _jlist(row.get("environments"))
    return envs or [{"name": row.get("active_environment") or "default", "base_url": row["base_url"]}]


def public_auth(row: dict) -> dict:
    """비밀 제외 — 환경변수 **이름**만."""
    kind = row.get("auth_kind") or "none"
    out: dict[str, Any] = {"kind": kind}
    if kind == "api_key":
        out.update(header=row.get("auth_header") if not row.get("auth_query_param") else None,
                   query_param=row.get("auth_query_param"), secret_env=row.get("auth_secret_env"))
    elif kind in ("bearer", "basic"):
        out.update(header=row.get("auth_header"), secret_env=row.get("auth_secret_env"))
    elif kind == "oauth2_client_credentials":
        out.update(token_url=row.get("auth_token_url"), client_id=row.get("auth_client_id"),
                   client_secret_env=row.get("auth_client_secret_env"), scopes=_jlist(row.get("auth_scopes")))
    elif kind == "login_token":
        out.update(login_config(row))
    return out


def login_config(row: dict) -> dict:
    """login_token 설정 (계약 §9.1) — env 이름만, 비밀 값 없음. 저장 행 → {token_url, login_body, …}."""
    try:
        cfg = json.loads(row.get("auth_login") or "{}")
    except ValueError:
        cfg = {}
    out = {"token_url": row.get("auth_token_url"), "login_body": cfg.get("login_body") or {}}
    for k in ("username_field", "username_env", "password_field", "password_env", "token_path", "scheme",
              "ttl_seconds"):
        out[k] = cfg.get(k, LOGIN_DEFAULTS.get(k))
    out["header"] = row.get("auth_header") or LOGIN_DEFAULTS["header"]
    return out


def _secretish(node: Any, path: str = "login_body") -> str | None:
    """login_body 안의 비밀처럼 보이는 키 (값이 있으면) — 비밀 값은 등록하지 않는다."""
    if isinstance(node, dict):
        for k, v in node.items():
            if str(k).lower() in SECRET_KEYS and v not in (None, ""):
                return f"{path}.{k}"
            hit = _secretish(v, f"{path}.{k}")
            if hit:
                return hit
    elif isinstance(node, list):
        for i, v in enumerate(node):
            hit = _secretish(v, f"{path}.{i}")
            if hit:
                return hit
    return None


def _login_auth(auth: dict) -> dict:
    token_url = str(auth.get("token_url") or "")
    if not token_url.startswith(("http://", "https://")):
        raise KineticError("invalid_params", "auth.token_url 은 http(s) URL 이어야 합니다.")
    body = auth.get("login_body")
    if body is None:
        body = {}
    if not isinstance(body, dict) or len(json.dumps(body, ensure_ascii=False)) > 4000:
        raise KineticError("invalid_params", "auth.login_body 는 객체(≤4000자)여야 합니다.")
    fields = {}
    for f in ("username_field", "password_field"):
        v = str(auth.get(f) or LOGIN_DEFAULTS[f])
        if not FIELD_RE.match(v):
            raise KineticError("invalid_params", f"auth.{f} 형식 오류.")
        fields[f] = v
    if fields["username_field"] == fields["password_field"]:
        raise KineticError("invalid_params", "auth.username_field 와 password_field 가 같습니다.")
    for f in fields.values():
        if f in body:
            raise KineticError("invalid_params", f"auth.login_body.{f}: 아이디·비밀번호는 env 이름(username_env·"
                                                 "password_env)으로 주세요.")
    leaked = _secretish(body)
    if leaked:
        raise KineticError("invalid_params", f"auth.{leaked}: 비밀 값은 등록하지 않습니다 — 환경변수 이름(*_env)을 주세요.")
    token_path = str(auth.get("token_path") or LOGIN_DEFAULTS["token_path"])
    if not TOKEN_PATH_RE.match(token_path):
        raise KineticError("invalid_params", "auth.token_path 는 점 경로여야 합니다 (예 token, data.accessToken).")
    header = str(auth.get("header") or LOGIN_DEFAULTS["header"])
    if not PARAM_NAME_RE.match(header):
        raise KineticError("invalid_params", "auth.header 형식 오류.")
    scheme = auth.get("scheme", LOGIN_DEFAULTS["scheme"])
    scheme = "" if scheme is None else str(scheme)
    if not SCHEME_RE.match(scheme):
        raise KineticError("invalid_params", "auth.scheme 형식 오류 (예 Bearer, 빈 문자열 = 토큰만).")
    try:
        ttl = int(auth.get("ttl_seconds") if auth.get("ttl_seconds") is not None else LOGIN_DEFAULTS["ttl_seconds"])
    except (TypeError, ValueError):
        raise KineticError("invalid_params", "auth.ttl_seconds 는 정수여야 합니다.") from None
    if not 60 <= ttl <= 86400:
        raise KineticError("invalid_params", "auth.ttl_seconds 는 60~86400.")
    cfg = {"login_body": body, **fields,
           "username_env": _env_name(auth.get("username_env"), "auth.username_env"),
           "password_env": _env_name(auth.get("password_env"), "auth.password_env"),
           "token_path": token_path, "scheme": scheme, "ttl_seconds": ttl}
    return {"auth_header": header, "auth_token_url": token_url, "auth_login": json.dumps(cfg, ensure_ascii=False)}


def _public(row: dict) -> dict:
    executable = is_executable(row)
    return {
        "name": row["name"], "display_name": row.get("display_name") or row["name"],
        "description": row.get("description") or "", "owner_team": row.get("owner_team") or "",
        "contact": row.get("contact") or "", "tags": _jlist(row.get("tags")), "icon": row.get("icon") or "generic",
        "protocol": protocol_of(row), "spec_format": row.get("spec_format"),
        "executable": executable, "adapter_required": not executable,
        "base_url": row["base_url"], "environments": environments_of(row),
        "active_environment": row.get("active_environment") or "default",
        "openapi_url": row.get("openapi_url"), "auth": public_auth(row),
        "auth_kind": row["auth_kind"], "auth_header": row["auth_header"],
        "auth_secret_env": row["auth_secret_env"], "timeout_ms": row["timeout_ms"],
        "retries": row["retries"] if row.get("retries") is not None else DEFAULT_RETRIES,
        "health_path": row.get("health_path") or "/health", "operations_count": len(merged_operations(row)),
        "route": f"/svc/{row['name']}", "created_at": row["created_at"],
        "updated_at": row.get("updated_at") or row["created_at"],
    }


DEFAULT_RETRIES = 2


def _base_url(value: Any, protocol: str = "rest") -> str:
    base_url = str(value or "").strip().rstrip("/")
    if protocol in ("rest", "odata", "soap", "graphql"):
        if not base_url.startswith(("http://", "https://")):
            raise KineticError("invalid_params", "base_url 은 http(s) URL 이어야 합니다.")
    elif not base_url or len(base_url) > 2000:  # grpc·db_procedure·async 는 http 가 아닐 수 있다
        raise KineticError("invalid_params", "base_url 이 필요합니다.")
    return base_url


def _env_name(value: Any, field: str) -> str:
    value = str(value or "")
    if not ENV_NAME_RE.match(value):
        raise KineticError("invalid_params", f"{field} 는 환경변수 이름이어야 합니다 (값 아님). 예: CMMS_API_KEY")
    return value


def _auth(auth: Any) -> dict:
    """auth → 저장 컬럼. 비밀 값은 받지 않는다 — 환경변수 이름만."""
    auth = auth or {}
    if not isinstance(auth, dict):
        raise KineticError("invalid_params", "auth 는 객체여야 합니다.")
    kind = auth.get("kind") or "none"
    if kind not in AUTH_KINDS:
        raise KineticError("invalid_params", f"auth.kind 는 {'|'.join(AUTH_KINDS)}.")
    for leaked in ("secret", "value", "password", "client_secret", "token", "api_key"):
        if auth.get(leaked):
            raise KineticError("invalid_params", f"auth.{leaked}: 비밀 값은 등록하지 않습니다 — 환경변수 이름(*_env)을 주세요.")
    row = {"auth_kind": kind, "auth_header": None, "auth_secret_env": None, "auth_query_param": None,
           "auth_token_url": None, "auth_client_id": None, "auth_client_secret_env": None, "auth_scopes": None,
           "auth_login": None}
    if kind == "none":
        return row
    if kind == "login_token":
        row.update(_login_auth(auth))
        return row
    if kind == "oauth2_client_credentials":
        token_url = str(auth.get("token_url") or "")
        if not token_url.startswith(("http://", "https://")):
            raise KineticError("invalid_params", "auth.token_url 은 http(s) URL 이어야 합니다.")
        client_id = str(auth.get("client_id") or "")
        if not client_id or len(client_id) > 200:
            raise KineticError("invalid_params", "auth.client_id 가 필요합니다.")
        scopes = auth.get("scopes") or []
        if isinstance(scopes, str):
            scopes = scopes.split()
        if not isinstance(scopes, list) or not all(isinstance(x, str) and x and " " not in x for x in scopes):
            raise KineticError("invalid_params", "auth.scopes 는 문자열 배열이어야 합니다.")
        row.update(auth_header="Authorization", auth_token_url=token_url, auth_client_id=client_id,
                   auth_client_secret_env=_env_name(auth.get("client_secret_env"), "auth.client_secret_env"),
                   auth_scopes=json.dumps(scopes))
        return row
    # api_key · basic · bearer — secret_env 하나 (basic 은 "user:password")
    secret_env = auth.get("secret_env")
    row["auth_secret_env"] = _env_name(secret_env, "auth.secret_env") if secret_env or kind == "basic" else None
    if kind == "api_key" and auth.get("query_param"):
        if auth.get("header"):
            raise KineticError("invalid_params", "api_key 는 header 와 query_param 중 하나만.")
        qp = str(auth["query_param"])
        if not PARAM_NAME_RE.match(qp):
            raise KineticError("invalid_params", "auth.query_param 형식 오류.")
        row["auth_query_param"] = qp
        return row
    header = str(auth.get("header") or _DEFAULT_HEADER[kind])
    if not PARAM_NAME_RE.match(header):
        raise KineticError("invalid_params", "auth.header 형식 오류.")
    row["auth_header"] = "Authorization" if kind == "basic" else header
    return row


def _health_path(value: Any) -> str:
    path = str(value or "/health")
    if not path.startswith("/"):
        raise KineticError("invalid_params", "health_path 는 '/' 로 시작해야 합니다.")
    return path


def _protocol(value: Any) -> str:
    protocol = str(value or "rest")
    if protocol not in PROTOCOLS:
        raise KineticError("invalid_params", f"protocol 은 {'|'.join(PROTOCOLS)}.")
    return protocol


def _retries(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise KineticError("invalid_params", "retries 는 0~5 정수여야 합니다.") from None
    if not 0 <= n <= 5:
        raise KineticError("invalid_params", "retries 는 0~5 정수여야 합니다.")
    return n


def _meta(body: dict, prev: dict) -> dict:
    """표시·소유 정보. 주지 않은 항목은 이전 값 유지 (등록 교체 시)."""
    out = {}
    for field, limit in (("display_name", 200), ("owner_team", 200), ("contact", 500)):
        if field in body:
            v = str(body[field] or "")
            if len(v) > limit:
                raise KineticError("invalid_params", f"{field} 가 너무 깁니다 (≤{limit}).")
            out[field] = v or None
        else:
            out[field] = prev.get(field)
    if "tags" in body:
        tags = body["tags"] or []
        if not isinstance(tags, list) or not all(isinstance(t, str) and 0 < len(t) <= 50 for t in tags) or len(tags) > 30:
            raise KineticError("invalid_params", "tags 는 문자열(≤50자) 배열(≤30개)이어야 합니다.")
        out["tags"] = json.dumps(list(dict.fromkeys(tags)), ensure_ascii=False)
    else:
        out["tags"] = prev.get("tags")
    if "icon" in body:
        icon = str(body["icon"] or "")
        if icon and not ICON_RE.match(icon):
            raise KineticError("invalid_params", "icon 은 소문자 키 (예 mes|cmms|aps|erp|sap|scm|wms|generic).")
        out["icon"] = icon or None
    else:
        out["icon"] = prev.get("icon")
    return out


def _environments(body: dict, protocol: str, current: dict | None = None) -> dict:
    """environments·active_environment·base_url → 저장 컬럼. base_url = 활성 환경 주소.

    - environments 를 주면 목록 교체(그때 base_url 은 활성 환경 고르기에만 쓴다 — 등록 시 같은 주소의 환경이 활성).
    - active_environment 는 전환 (목록에 있어야 한다). 목록 없이 주면 하나짜리 환경의 이름.
    - environments 없이 base_url 만 주면 활성 환경의 주소를 바꾼다 (등록 = 'default' 하나).
    """
    if current is not None:
        envs = environments_of(current)
        active = current.get("active_environment") or envs[0]["name"]
    else:
        envs, active = [], None
    raw = body.get("environments")
    if raw is not None:
        if not isinstance(raw, list) or not raw:
            raise KineticError("invalid_params", "environments 는 [{name, base_url}] 배열이어야 합니다.")
        envs = []
        for e in raw:
            if not isinstance(e, dict) or not ENV_LABEL_RE.match(str(e.get("name") or "")):
                raise KineticError("invalid_params", "environments[].name 형식 오류 (영문·숫자·_ . -).")
            if any(x["name"] == e["name"] for x in envs):
                raise KineticError("invalid_params", f"환경 이름 '{e['name']}' 이 중복됩니다.")
            envs.append({"name": e["name"], "base_url": _base_url(e.get("base_url"), protocol)})
        if current is None and body.get("base_url") and not body.get("active_environment"):
            url = str(body["base_url"]).strip().rstrip("/")
            active = next((e["name"] for e in envs if e["base_url"] == url), None)
        if active not in {e["name"] for e in envs}:
            active = envs[0]["name"]
    want = body.get("active_environment")
    if want:
        want = str(want)
        if not ENV_LABEL_RE.match(want):
            raise KineticError("invalid_params", "active_environment 형식 오류.")
        if envs and want not in {e["name"] for e in envs}:
            raise KineticError("invalid_params", f"active_environment '{want}' 이 environments 에 없습니다.")
        active = want
    if not envs:
        envs = [{"name": active or "default", "base_url": _base_url(body.get("base_url"), protocol)}]
        active = envs[0]["name"]
    elif raw is None and body.get("base_url") is not None:
        url = _base_url(body["base_url"], protocol)
        envs = [{**e, "base_url": url} if e["name"] == active else e for e in envs]
    base = next(e["base_url"] for e in envs if e["name"] == active)
    return {"base_url": base, "environments": json.dumps(envs, ensure_ascii=False), "active_environment": active}


def validate_operation(body: Any) -> dict:
    """수동 등록 Operation 검증. path 의 {변수} 는 parameters 에 in:path 로 있어야 한다."""
    if not isinstance(body, dict):
        raise KineticError("invalid_params", "Operation 객체가 필요합니다.")
    op_id = str(body.get("operation_id") or "")
    if not OP_ID_RE.match(op_id):
        raise KineticError("invalid_params", "operation_id 형식 오류 (영문·숫자·_ . -).")
    method = str(body.get("method") or "").lower()
    if method not in METHODS:
        raise KineticError("invalid_params", f"method 는 {'|'.join(m.upper() for m in METHODS)}.")
    path = str(body.get("path") or "")
    if not path.startswith("/"):
        raise KineticError("invalid_params", "path 는 '/' 로 시작해야 합니다.")
    params = []
    for p in body.get("parameters") or []:
        if not isinstance(p, dict) or not p.get("name") or p.get("in") not in PARAM_IN:
            raise KineticError("invalid_params", "parameters 항목은 {name, in: path|query|header} 이어야 합니다.")
        params.append({"name": str(p["name"]), "in": p["in"], "required": bool(p.get("required") or p["in"] == "path"),
                       "schema": p.get("schema") or {}})
    declared = {p["name"] for p in params if p["in"] == "path"}
    missing = [v for v in re.findall(r"\{([^}]+)\}", path) if v not in declared]
    if missing:
        raise KineticError("invalid_params", f"경로 변수 {missing} 가 parameters(in: path) 에 없습니다.")
    schema = body.get("request_body_schema")
    if schema is not None and not isinstance(schema, dict):
        raise KineticError("invalid_params", "request_body_schema 는 JSON Schema 객체여야 합니다.")
    return {"operation_id": op_id, "method": method.upper(), "path": path, "summary": str(body.get("summary") or ""),
            "parameters": params, "request_body_schema": schema}


class Registry:
    def __init__(self, store: Store, http: httpx.AsyncClient):
        self.store = store
        self.http = http
        self._ops: dict[str, dict[str, dict]] = {}

    async def _fetch(self, url: str) -> str:
        try:
            r = await self.http.get(url, timeout=10)
            r.raise_for_status()
            return r.text
        except Exception as exc:
            raise KineticError("invalid_params", f"스펙을 가져오지 못했습니다: {exc}") from exc

    async def intake(self, body: dict) -> dict:
        """스펙 입수 — openapi(객체) > openapi_text(원문) > openapi_url(가져오기). → {openapi, spec_format, spec_text}.
        Swagger 2.0 은 OpenAPI 3 로 바꿔 저장한다. 스펙이 없으면 빈 명세(수동 API 만)."""
        declared = body.get("spec_format") or None
        if declared is not None and declared not in SPEC_FORMATS:
            raise KineticError("invalid_params", f"spec_format 은 {'|'.join(SPEC_FORMATS)}.")
        doc: Any = None
        fmt: str | None = None
        if body.get("openapi") is not None:
            doc = body["openapi"]
            if not isinstance(doc, dict):
                raise KineticError("invalid_params", "openapi 는 객체여야 합니다.")
            fmt = detect_format(doc)
        elif body.get("openapi_text"):
            doc, fmt = load_text(body["openapi_text"])
        elif body.get("openapi_url"):
            doc, fmt = load_text(await self._fetch(body["openapi_url"]))
        if doc is None:
            return {"openapi": "{}", "spec_format": declared, "spec_text": None}
        fmt = fmt or declared
        if fmt is None:
            if isinstance(doc, dict) and not doc:
                return {"openapi": "{}", "spec_format": declared, "spec_text": None}
            raise KineticError("invalid_params", "스펙 형식을 알 수 없습니다 (openapi3·swagger2·wsdl·graphql_sdl·proto·"
                                                 "asyncapi·odata_metadata).")
        if fmt == "swagger2":
            doc = swagger2_to_openapi3(doc)
        if fmt in ("openapi3", "swagger2"):
            return {"openapi": json.dumps(doc, ensure_ascii=False), "spec_format": fmt, "spec_text": None}
        text = doc if isinstance(doc, str) else json.dumps(doc, ensure_ascii=False)
        return {"openapi": "{}", "spec_format": fmt, "spec_text": text}

    @staticmethod
    def _protocol_for(body: dict, spec_format: str | None, prev: dict) -> str:
        if body.get("protocol"):
            return _protocol(body["protocol"])
        if spec_format in FORMAT_PROTOCOL:
            return FORMAT_PROTOCOL[spec_format]
        return prev.get("protocol") or "rest"

    def _save(self, row: dict) -> dict:
        self.store.upsert_system(row)
        self._ops.pop(row["name"], None)
        return _public(row)

    async def register(self, body: dict) -> dict:
        """등록(같은 이름이면 교체). 수동 등록 operation 과 created_at 은 유지한다.
        openapi·openapi_text·openapi_url 모두 없으면 빈 명세 — 수동 등록 API 만 쓰는 시스템."""
        name = str(body.get("name") or "")
        if not SYSTEM_NAME_RE.match(name) or name in RESERVED:
            raise KineticError("invalid_params", "name 은 소문자·숫자·'-' 만 허용됩니다 ('routes' 제외).")
        prev = self.store.get_system(name) or {}
        spec = await self.intake(body)
        protocol = self._protocol_for(body, spec["spec_format"], {})
        envs = _environments(body, protocol)
        now = now_iso()
        row = {
            "name": name, **envs, **spec, **_auth(body.get("auth")), **_meta(body, prev), "protocol": protocol,
            "timeout_ms": _timeout(body.get("timeout_ms"), 10000), "created_at": prev.get("created_at") or now,
            "retries": _retries(body["retries"]) if body.get("retries") is not None else None,
            "description": str(body.get("description") or prev.get("description") or ""),
            "openapi_url": body.get("openapi_url") or None, "health_path": _health_path(body.get("health_path")),
            "manual_ops": prev.get("manual_ops") or "[]", "updated_at": now,
        }
        return self._save(row)

    async def test(self, body: dict, *, direct: bool) -> dict:
        """연결 테스트 — 저장하지 않는다. 스펙 파싱 · health 직접 호출 · 인증 env 존재 여부(값은 보지 않음)."""
        auth_row = _auth(body.get("auth"))
        out: dict[str, Any] = {}
        try:
            spec = await self.intake(body)
        except KineticError as exc:
            spec = None
            out["spec"] = {"ok": False, "format": body.get("spec_format"), "operations": 0, "error": exc.message}
        protocol = self._protocol_for(body, spec["spec_format"] if spec else body.get("spec_format"), {})
        try:
            envs = _environments(body, protocol)
        except KineticError as exc:
            envs = None
            out["health"] = {"ok": False, "http_status": None, "latency_ms": None, "error": exc.message}
        if spec is not None:
            row = {"openapi": spec["openapi"], "spec_format": spec["spec_format"], "spec_text": spec["spec_text"],
                   "base_url": envs["base_url"] if envs else None}
            ops = spec_operations(row)
            has_spec = bool(body.get("openapi") or body.get("openapi_text") or body.get("openapi_url"))
            out["spec"] = {"ok": True, "format": spec["spec_format"], "operations": len(ops),
                           "operation_ids": [o["operation_id"] for o in ops][:200]}
            if not has_spec:
                out["spec"]["note"] = "스펙 없음 — 수동 등록 API 만 쓰는 시스템"
        if envs is not None:
            url = envs["base_url"] + _health_path(body.get("health_path"))
            if not url.startswith(("http://", "https://")):
                out["health"] = {"ok": False, "http_status": None, "latency_ms": None, "url": url,
                                 "error": "http(s) 주소가 아니라 health 를 부를 수 없습니다 (어댑터 필요)."}
            else:
                t0 = time.perf_counter()
                try:
                    r = await self.http.get(url, timeout=3)
                    status, error = r.status_code, None if r.status_code < 300 else f"HTTP {r.status_code}"
                except httpx.HTTPError as exc:
                    status, error = None, f"{type(exc).__name__}: {exc}"
                out["health"] = {"ok": error is None, "http_status": status, "url": url,
                                 "latency_ms": round((time.perf_counter() - t0) * 1000), **({"error": error} if error else {})}
        need = required_envs(auth_row)
        missing = [e for e in need if not os.environ.get(e)]
        out["auth"] = {"ok": not missing, "kind": auth_row["auth_kind"], "required_env": need, "missing_env": missing,
                       "checked_in": "kinetic-action",
                       "injected_by": "kinetic-action" if direct else "api-gateway"}
        executable = protocol in EXECUTABLE_PROTOCOLS
        out.update(protocol=protocol, executable=executable, adapter_required=not executable,
                   ok=all(out[k]["ok"] for k in ("spec", "health", "auth")))
        return out

    async def patch(self, name: str, body: dict) -> dict:
        row = dict(self.system(name))
        if "description" in body:
            row["description"] = str(body["description"] or "")
        row.update(_meta(body, row))
        if body.get("protocol"):
            row["protocol"] = _protocol(body["protocol"])
        if any(k in body for k in ("environments", "active_environment", "base_url")):
            row.update(_environments(body, protocol_of(row), current=row))
        if "auth" in body:
            row.update(_auth(body["auth"]))
        if "timeout_ms" in body:
            row["timeout_ms"] = _timeout(body["timeout_ms"], row["timeout_ms"])
        if "retries" in body:
            row["retries"] = _retries(body["retries"]) if body["retries"] is not None else None
        if "health_path" in body:
            row["health_path"] = _health_path(body["health_path"])
        if "openapi_url" in body:  # 주소만 바꾼다. operation 갱신은 refresh
            row["openapi_url"] = body["openapi_url"] or None
        if body.get("openapi") is not None or body.get("openapi_text"):  # 스펙 교체 (업로드)
            row.update(await self.intake({k: body[k] for k in ("openapi", "openapi_text", "spec_format") if k in body}))
        row["updated_at"] = now_iso()
        return self._save(row)

    def delete(self, name: str) -> None:
        self.system(name)
        self.store.delete_system(name)
        self._ops.pop(name, None)

    async def refresh(self, name: str) -> dict:
        row = dict(self.system(name))
        if not row.get("openapi_url"):
            raise KineticError("invalid_params", f"시스템 '{name}' 에 openapi_url 이 없습니다.")
        row.update(await self.intake({"openapi_url": row["openapi_url"], "spec_format": row.get("spec_format")}))
        row["updated_at"] = now_iso()
        return self._save(row)

    def add_operation(self, name: str, body: dict) -> dict:
        row = dict(self.system(name))
        op = validate_operation(body)
        row["manual_ops"] = json.dumps([*(o for o in _manual(row) if o["operation_id"] != op["operation_id"]), op],
                                       ensure_ascii=False)
        row["updated_at"] = now_iso()
        self._save(row)
        return {**op, "source": "manual"}

    def delete_operation(self, name: str, operation_id: str) -> None:
        row = dict(self.system(name))
        manual = _manual(row)
        if not any(o["operation_id"] == operation_id for o in manual):
            if operation_id in merged_operations(row):
                raise KineticError("conflict", "스펙에서 온 operation 은 지울 수 없습니다 (명세를 고치고 refresh).")
            raise KineticError("not_found", f"operation '{operation_id}' 이 없습니다.")
        row["manual_ops"] = json.dumps([o for o in manual if o["operation_id"] != operation_id], ensure_ascii=False)
        row["updated_at"] = now_iso()
        self._save(row)

    def list(self) -> list[dict]:
        return [_public(r) for r in self.store.list_systems()]

    def get(self, name: str) -> dict:
        return {**_public(self.system(name)), "operations": self.operations(name)}

    def system(self, name: str) -> dict:
        row = self.store.get_system(name)
        if not row:
            raise KineticError("not_found", f"시스템 '{name}' 이 등록되지 않았습니다.")
        return row

    def require_executable(self, name: str) -> None:
        row = self.system(name)
        if not is_executable(row):
            raise KineticError("not_executable", f"시스템 '{name}' 은 protocol '{protocol_of(row)}' 라 어댑터가 필요합니다 "
                                                 "(현재 실행 가능: rest·odata).")

    def operations(self, name: str, method: str | None = None) -> list[dict]:
        if name not in self._ops:
            self._ops[name] = merged_operations(self.system(name))
        ops = list(self._ops[name].values())
        if method:
            ops = [o for o in ops if str(o.get("method") or "").upper() == method.upper()]
        return ops

    def operation(self, name: str, operation_id: str) -> dict:
        for op in self.operations(name):
            if op["operation_id"] == operation_id:
                return op
        raise KineticError("not_found", f"시스템 '{name}' 에 operationId '{operation_id}' 가 없습니다.")

    def routes(self) -> list[dict]:
        """게이트웨이 동적 라우트 원천 — 실행 가능한(http) 시스템만. 비밀 값 없음(환경변수 이름만)."""
        out = []
        for r in self.store.list_systems():
            if not is_executable(r):
                continue
            kind = r["auth_kind"] or "none"
            route = {
                "id": f"svc-{r['name']}", "system": r["name"], "path_prefix": f"/svc/{r['name']}",
                "uri": r["base_url"], "auth_header": None, "auth_value_env": None, "timeout_ms": r["timeout_ms"],
                "auth_kind": kind, "auth_query_param": None, "basic_env": None, "oauth2": None, "login_token": None,
                "retries": r["retries"] if r.get("retries") is not None else DEFAULT_RETRIES,
            }
            if kind == "api_key":
                if r.get("auth_query_param"):
                    route.update(auth_query_param=r["auth_query_param"], auth_value_env=r["auth_secret_env"])
                else:
                    route.update(auth_header=r["auth_header"], auth_value_env=r["auth_secret_env"])
            elif kind == "bearer":
                route.update(auth_header=r["auth_header"], auth_value_env=r["auth_secret_env"])
            elif kind == "basic":
                route.update(basic_env=r["auth_secret_env"])
            elif kind == "oauth2_client_credentials":
                route["oauth2"] = {"token_url": r["auth_token_url"], "client_id": r["auth_client_id"],
                                   "client_secret_env": r["auth_client_secret_env"],
                                   "scopes": _jlist(r.get("auth_scopes"))}
            elif kind == "login_token":
                route["login_token"] = login_config(r)
            out.append(route)
        return out


def _timeout(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        raise KineticError("invalid_params", "timeout_ms 는 정수여야 합니다.") from None
