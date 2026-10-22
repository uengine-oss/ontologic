"""개발용 IdP — **운영 금지 (DEV ONLY)**.

인증 없이 누구에게나 원하는 sub·roles 로 토큰을 발급한다. 데모와 테스트에서 JWKS 기반 RS256
검증 경로를 실제로 태우기 위한 것일 뿐이다. 실제 환경은 Keycloak 등 진짜 IdP 의 JWKS 를
`KINETIC_JWKS_URL` 로 가리킨다.

- RSA 키를 `.keys/dev_idp_key.pem` 에 만들어 둔다 (gitignore).
- `GET /.well-known/jwks.json`, `POST /token {sub, roles, plant, ...}` → JWT (1시간)
- `POST /oauth/token` — OAuth2 **client credentials** 그랜트 (RFC 6749 §4.4, form). 등록 클라이언트
  `kinetic-gateway`(비밀 = env `KINETIC_GATEWAY_CLIENT_SECRET`, 기본 `aps-demo-secret`) 에게
  `aud: mock-aps` 서비스 토큰을 준다. 이건 비밀을 확인한다 — 하위 서비스(mock-aps)가 진짜로 검증하는 경로.
  `GET /oauth/stats` = 발급 횟수 (게이트웨이 토큰 캐시 확인용), `POST /oauth/stats/reset`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from urllib.parse import parse_qs

import jwt
import uvicorn
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse

ISSUER = os.environ.get("DEV_IDP_ISSUER", "http://localhost:8032")
AUDIENCE = os.environ.get("DEV_IDP_AUDIENCE", "kinetic-action")
SERVICE_TOKEN_TTL = int(os.environ.get("DEV_IDP_SERVICE_TOKEN_TTL", "3600"))
# client credentials 클라이언트: client_id → (비밀, 토큰 aud, 허용 scope)
CLIENTS = {
    "kinetic-gateway": (os.environ.get("KINETIC_GATEWAY_CLIENT_SECRET", "aps-demo-secret"), "mock-aps",
                        {"aps.write", "aps.read"}),
}
STATS = {"token_requests": 0, "issued": 0, "rejected": 0}
KEY_DIR = Path(os.environ.get("DEV_IDP_KEY_DIR", Path(__file__).parent / ".keys"))


def _load_key():
    path = KEY_DIR / "dev_idp_key.pem"
    if path.exists():
        return serialization.load_pem_private_key(path.read_bytes(), password=None)
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    path.chmod(0o600)
    return key


KEY = _load_key()
JWK = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key()))
KID = hashlib.sha256(JWK["n"].encode()).hexdigest()[:16]
JWK.update(kid=KID, use="sig", alg="RS256")

app = FastAPI(title="dev-idp (DEV ONLY — 운영 금지)")


@app.get("/.well-known/jwks.json")
def jwks():
    return {"keys": [JWK]}


@app.get("/.well-known/openid-configuration")
def discovery():
    return {"issuer": ISSUER, "jwks_uri": f"{ISSUER}/.well-known/jwks.json", "token_endpoint": f"{ISSUER}/oauth/token",
            "grant_types_supported": ["client_credentials"],
            "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"]}


def _oauth_error(code: str, status: int = 400) -> JSONResponse:
    STATS["rejected"] += 1
    return JSONResponse({"error": code}, status_code=status, headers={"Cache-Control": "no-store"})


@app.post("/oauth/token")
async def oauth_token(request: Request):
    """OAuth2 client credentials (form). client_secret_post 또는 client_secret_basic."""
    STATS["token_requests"] += 1
    form = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
    client_id, secret = form.get("client_id"), form.get("client_secret")
    basic = request.headers.get("authorization", "")
    if basic.lower().startswith("basic "):
        try:
            client_id, _, secret = base64.b64decode(basic[6:]).decode().partition(":")
        except ValueError:
            return _oauth_error("invalid_client", 401)
    if form.get("grant_type") != "client_credentials":
        return _oauth_error("unsupported_grant_type")
    client = CLIENTS.get(client_id or "")
    if client is None or not hmac.compare_digest((secret or "").encode(), client[0].encode()):
        return _oauth_error("invalid_client", 401)
    requested = set((form.get("scope") or "").split())
    if requested - client[2]:
        return _oauth_error("invalid_scope")
    scope = " ".join(sorted(requested or client[2]))
    now = int(time.time())
    claims = {"sub": client_id, "client_id": client_id, "scope": scope, "iss": ISSUER, "aud": client[1],
              "iat": now, "exp": now + SERVICE_TOKEN_TTL, "token_use": "service"}
    STATS["issued"] += 1
    return JSONResponse({"access_token": jwt.encode(claims, KEY, algorithm="RS256", headers={"kid": KID}),
                         "token_type": "Bearer", "expires_in": SERVICE_TOKEN_TTL, "scope": scope},
                        headers={"Cache-Control": "no-store"})


@app.get("/oauth/stats")
def oauth_stats():
    return STATS


@app.post("/oauth/stats/reset")
def oauth_stats_reset():
    STATS.update(token_requests=0, issued=0, rejected=0)
    return STATS


@app.post("/token")
def token(body: dict = Body(...)):
    """⚠ DEV ONLY: 아무 인증 없이 요청한 클레임으로 토큰을 만든다."""
    now = int(time.time())
    claims = {k: v for k, v in body.items() if k not in ("iss", "aud", "exp", "iat")}
    claims.setdefault("sub", "anonymous")
    claims["roles"] = list(claims.get("roles") or [])
    claims.update(iss=ISSUER, aud=AUDIENCE, iat=now, exp=now + 3600)
    return {"access_token": jwt.encode(claims, KEY, algorithm="RS256", headers={"kid": KID}),
            "token_type": "Bearer", "expires_in": 3600}


if __name__ == "__main__":
    print("⚠⚠⚠  dev-idp: 개발 전용 IdP 입니다. 누구에게나 토큰을 발급합니다. 운영에 쓰지 마세요.  ⚠⚠⚠")
    uvicorn.run(app, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8032")))
