"""JWT 검증과 호출자(actor) 구성. 계약 §2.

- RS256 + JWKS(`KINETIC_JWKS_URL`). `KINETIC_ISSUER` 가 비어 있으면 iss 는 검사하지 않는다.
- actor = 클레임 맵 그대로. `roles` 는 항상 문자열 배열로 정규화한다.
- 401 에는 RFC 9728 `resource_metadata` 를 담은 WWW-Authenticate 를 단다.
"""

from __future__ import annotations

import os

from typing import Any, Callable

import jwt

from .config import Settings
from .errors import KineticError

ROLE_APPROVER = "kinetic_approver"
ROLE_ADMIN = "kinetic_admin"

KeyResolver = Callable[[str], Any]


def www_authenticate(settings: Settings) -> str:
    return f'Bearer resource_metadata="{settings.public_base}/.well-known/oauth-protected-resource"'


def resource_metadata(settings: Settings) -> dict:
    return {
        "resource": settings.public_base,
        "authorization_servers": [settings.issuer] if settings.issuer else [],
        "bearer_methods_supported": ["header"],
        "scopes_supported": [],
    }


class Verifier:
    """토큰 → actor. 키 해석은 주입 가능(테스트는 고정 공개키를 넘긴다)."""

    def __init__(self, settings: Settings, key_resolver: KeyResolver | None = None):
        self.settings = settings
        if key_resolver is None:
            client = jwt.PyJWKClient(settings.jwks_url, cache_keys=True, lifespan=300) if settings.jwks_url else None

            def key_resolver(token: str):
                if client is None:
                    raise KineticError("unauthenticated", "KINETIC_JWKS_URL 이 설정되지 않았습니다.")
                return client.get_signing_key_from_jwt(token).key

        self._resolve = key_resolver

    def verify(self, token: str) -> dict:
        try:
            key = self._resolve(token)
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self.settings.audience or None,
                issuer=self.settings.issuer or None,
                options={"require": ["sub", "exp"]},
                # 발급 서버와 시계가 조금 어긋나도 막 받은 토큰이 「아직 유효하지 않음(iat)」으로 거부되지 않게
                leeway=int(os.environ.get("KINETIC_JWT_LEEWAY", "30")),
            )
        except KineticError:
            raise
        except Exception as exc:  # 만료·서명·aud·JWKS 조회 실패 모두 401
            raise KineticError("unauthenticated", f"토큰 검증 실패: {exc}") from exc
        roles = claims.get("roles") or []
        claims["roles"] = [roles] if isinstance(roles, str) else [str(r) for r in roles]
        return claims

    def from_header(self, authorization: str | None) -> dict:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise KineticError("unauthenticated", "Bearer 토큰이 필요합니다.")
        return self.verify(authorization.split(" ", 1)[1].strip())


def require_role(actor: dict, role: str) -> None:
    if role not in actor.get("roles", []):
        raise KineticError("forbidden", f"역할 '{role}' 이 필요합니다.")
