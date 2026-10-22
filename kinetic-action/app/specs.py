"""스펙 입수 — 원문(JSON·YAML·XML·SDL…) 판별, Swagger 2.0 → OpenAPI 3 변환, WSDL operation 이름 추출. 계약 §8.

실행기는 항상 "HTTP + JSON operation" 하나만 본다. 여기서는 등록 시점에 스펙을 OpenAPI 3 로 맞추거나
(swagger2), 어댑터가 필요한 형식(wsdl·graphql_sdl·proto·asyncapi)은 원문만 보관하고 operation 이름만 뽑는다.
"""

from __future__ import annotations

import json
import re
from typing import Any

import yaml

from .errors import KineticError

SPEC_FORMATS = ("openapi3", "swagger2", "wsdl", "graphql_sdl", "proto", "asyncapi", "odata_metadata")
# 스펙 형식 → 기본 프로토콜 (protocol 을 주지 않았을 때)
FORMAT_PROTOCOL = {"wsdl": "soap", "graphql_sdl": "graphql", "proto": "grpc", "asyncapi": "async",
                   "odata_metadata": "odata"}
OBJECT_FORMATS = ("openapi3", "swagger2", "asyncapi")  # JSON/YAML 객체로 읽는 형식


def detect_format(doc: Any) -> str | None:
    """객체(dict) 또는 원문(str) 의 스펙 형식. 모르면 None."""
    if isinstance(doc, dict):
        if str(doc.get("swagger", "")).startswith("2"):
            return "swagger2"
        if str(doc.get("openapi", "")).startswith("3"):
            return "openapi3"
        if "asyncapi" in doc:
            return "asyncapi"
        if "paths" in doc:
            return "openapi3"
        return None
    text = str(doc or "").lstrip("﻿").strip()
    if not text:
        return None
    if text.startswith("<"):
        if re.search(r"<(\w+:)?Edmx\b", text):
            return "odata_metadata"
        if re.search(r"<(\w+:)?definitions\b", text) or re.search(r"<(\w+:)?description\b[^>]*wsdl", text):
            return "wsdl"
        return None
    if re.search(r'^\s*syntax\s*=\s*"proto[23]"', text, re.M) or re.search(r"^\s*service\s+\w+\s*\{", text, re.M) \
            and re.search(r"\brpc\s+\w+\s*\(", text):
        return "proto"
    if re.search(r"^\s*(type|schema|extend\s+type)\s+(Query|Mutation|\w+)\s*\{", text, re.M) \
            or re.search(r"^\s*schema\s*\{", text, re.M):
        return "graphql_sdl"
    return None


def load_text(text: str) -> tuple[Any, str | None]:
    """원문 → (객체 또는 원문 그대로, 형식). JSON 먼저, 다음 YAML. XML·SDL·proto 는 원문을 돌려준다."""
    if not isinstance(text, str) or not text.strip():
        raise KineticError("invalid_params", "스펙 원문이 비어 있습니다.")
    raw_fmt = detect_format(text)
    if raw_fmt in ("wsdl", "odata_metadata", "proto", "graphql_sdl"):
        return text, raw_fmt
    try:
        doc = json.loads(text)
    except ValueError:
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise KineticError("invalid_params", f"스펙을 JSON·YAML 로 읽지 못했습니다: {exc}") from None
    if not isinstance(doc, dict):
        raise KineticError("invalid_params", "스펙 문서가 객체(JSON/YAML 매핑)가 아닙니다.")
    return doc, detect_format(doc)


# ── Swagger 2.0 → OpenAPI 3 ──

_SCHEMA_KEYS = ("type", "format", "items", "enum", "default", "minimum", "maximum", "pattern", "minLength",
                "maxLength", "collectionFormat", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "maxItems",
                "minItems", "uniqueItems")


def _refs(node: Any) -> Any:
    """`#/definitions/X` → `#/components/schemas/X` (재귀)."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str) and v.startswith("#/definitions/"):
                out[k] = "#/components/schemas/" + v[len("#/definitions/"):]
            else:
                out[k] = _refs(v)
        return out
    if isinstance(node, list):
        return [_refs(v) for v in node]
    return node


def _param_ref(p: Any, spec: dict) -> Any:
    if isinstance(p, dict) and isinstance(p.get("$ref"), str) and p["$ref"].startswith("#/parameters/"):
        return (spec.get("parameters") or {}).get(p["$ref"][len("#/parameters/"):], {})
    return p


def _convert_params(params: list, spec: dict, consumes: list[str]) -> tuple[list, dict | None]:
    out, body, form = [], None, {}
    for p in params or []:
        p = _param_ref(p, spec)
        if not isinstance(p, dict):
            continue
        where = p.get("in")
        if where == "body":
            ctype = next((c for c in consumes if "json" in c), consumes[0] if consumes else "application/json")
            body = {"required": bool(p.get("required")),
                    "content": {ctype: {"schema": _refs(p.get("schema") or {})}}}
            if p.get("description"):
                body["description"] = p["description"]
        elif where == "formData":
            form[p.get("name")] = {"schema": {k: _refs(p[k]) for k in _SCHEMA_KEYS if k in p and k != "collectionFormat"},
                                   "required": bool(p.get("required"))}
        elif where in ("path", "query", "header", "cookie"):
            schema = {k: _refs(p[k]) for k in _SCHEMA_KEYS if k in p and k != "collectionFormat"}
            q = {"name": p.get("name"), "in": where, "required": bool(p.get("required") or where == "path"),
                 "schema": schema}
            if p.get("description"):
                q["description"] = p["description"]
            out.append(q)
    if form and body is None:
        ctype = "multipart/form-data" if "multipart/form-data" in consumes else "application/x-www-form-urlencoded"
        body = {"content": {ctype: {"schema": {
            "type": "object", "properties": {n: f["schema"] for n, f in form.items()},
            **({"required": [n for n, f in form.items() if f["required"]]} if any(f["required"] for f in form.values())
               else {})}}}}
    return out, body


def swagger2_to_openapi3(spec: dict) -> dict:
    """최소 변환 — paths·parameters(body/formData/path/query/header)·responses·definitions·basePath/host/schemes.
    결과는 `servers[0].url = <scheme>://<host><basePath>` (host 가 없으면 basePath 만, 상대 URL)."""
    host = spec.get("host") or ""
    base_path = spec.get("basePath") or ""
    if base_path == "/":
        base_path = ""
    schemes = spec.get("schemes") or ["https"]
    scheme = "https" if "https" in schemes else schemes[0]
    url = f"{scheme}://{host}{base_path}" if host else (base_path or "/")
    g_consumes = spec.get("consumes") or ["application/json"]
    g_produces = spec.get("produces") or ["application/json"]
    paths: dict = {}
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        new_item: dict = {}
        common, _ = _convert_params(item.get("parameters") or [], spec, g_consumes)
        if common:
            new_item["parameters"] = common
        for method, op in item.items():
            if method not in ("get", "post", "put", "patch", "delete", "head", "options") or not isinstance(op, dict):
                continue
            consumes = op.get("consumes") or g_consumes
            produces = op.get("produces") or g_produces
            params, body = _convert_params(op.get("parameters") or [], spec, consumes)
            if body is None:  # 경로 공통 body 파라미터
                _, body = _convert_params(item.get("parameters") or [], spec, consumes)
            new_op = {k: op[k] for k in ("operationId", "summary", "description", "tags", "deprecated") if k in op}
            if params:
                new_op["parameters"] = params
            if body:
                new_op["requestBody"] = body
            responses = {}
            for code, resp in (op.get("responses") or {}).items():
                resp = resp if isinstance(resp, dict) else {}
                r = {"description": resp.get("description") or ""}
                if resp.get("schema") is not None:
                    r["content"] = {(produces[0] if produces else "application/json"): {"schema": _refs(resp["schema"])}}
                responses[str(code)] = r
            new_op["responses"] = responses or {"default": {"description": ""}}
            new_item[method] = new_op
        paths[path] = new_item
    out = {"openapi": "3.0.3", "info": spec.get("info") or {"title": "converted", "version": "1"},
           "servers": [{"url": url}], "paths": paths,
           "components": {"schemas": _refs(spec.get("definitions") or {})},
           "x-kinetic-converted-from": "swagger2"}
    sec = {}
    for name, d in (spec.get("securityDefinitions") or {}).items():
        if d.get("type") == "basic":
            sec[name] = {"type": "http", "scheme": "basic"}
        elif d.get("type") == "apiKey":
            sec[name] = {"type": "apiKey", "name": d.get("name"), "in": d.get("in")}
        elif d.get("type") == "oauth2":
            flow = {"application": "clientCredentials", "accessCode": "authorizationCode"}.get(d.get("flow"),
                                                                                              d.get("flow"))
            sec[name] = {"type": "oauth2", "flows": {flow: {k: d[k] for k in ("tokenUrl", "authorizationUrl", "scopes")
                                                            if k in d}}}
    if sec:
        out["components"]["securitySchemes"] = sec
    return out


# ── WSDL: operation 이름만 (어댑터 필요 — 실행하지 않는다) ──

def wsdl_operations(text: str) -> list[dict]:
    names: list[str] = []
    for block in re.findall(r"<(?:\w+:)?(?:portType|interface)\b.*?</(?:\w+:)?(?:portType|interface)>", text, re.S):
        for name in re.findall(r"<(?:\w+:)?operation\s+[^>]*?name=\"([^\"]+)\"", block):
            if name not in names:
                names.append(name)
    return [{"operation_id": n, "method": "POST", "path": "/", "summary": "SOAP operation (어댑터 필요)",
             "parameters": [], "request_body_schema": None} for n in names]
