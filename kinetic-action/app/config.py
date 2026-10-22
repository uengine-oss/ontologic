"""환경 설정. 계약(specs/014-kinetic-action-layer/contracts/kinetic-api.md) 의 env 이름을 그대로 쓴다."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Settings:
    db_url: str = "sqlite:///./kinetic.db"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str | None = None
    jwks_url: str = ""
    issuer: str = ""
    audience: str = "kinetic-action"
    internal_secret: str = ""
    public_base: str = "http://localhost:8030"
    svc_base: str = "http://localhost:9000/svc"
    svc_direct: bool = False
    concurrency: int = 8
    max_attempts: int = 3
    plan_ttl: int = 600
    catalog_refresh: float = 30.0
    port: int = 8030
    query_max_items: int = 500
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            db_url=_env("KINETIC_DB_URL", "sqlite:///./kinetic.db"),
            neo4j_uri=_env("KINETIC_NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=_env("KINETIC_NEO4J_USER", "neo4j"),
            neo4j_password=_env("KINETIC_NEO4J_PASSWORD"),
            neo4j_database=_env("KINETIC_NEO4J_DATABASE") or None,
            jwks_url=_env("KINETIC_JWKS_URL"),
            issuer=_env("KINETIC_ISSUER"),
            audience=_env("KINETIC_AUDIENCE", "kinetic-action"),
            internal_secret=_env("KINETIC_INTERNAL_SECRET"),
            public_base=_env("KINETIC_PUBLIC_BASE", "http://localhost:8030").rstrip("/"),
            svc_base=_env("KINETIC_SVC_BASE", "http://localhost:9000/svc").rstrip("/"),
            svc_direct=_env("KINETIC_SVC_DIRECT") in ("1", "true", "yes"),
            concurrency=int(_env("KINETIC_CONCURRENCY", "8")),
            max_attempts=int(_env("KINETIC_MAX_ATTEMPTS", "3")),
            plan_ttl=int(_env("KINETIC_PLAN_TTL", "600")),
            catalog_refresh=float(_env("KINETIC_CATALOG_REFRESH", "30")),
            port=int(_env("KINETIC_PORT", "8030")),
            query_max_items=int(_env("KINETIC_QUERY_MAX_ITEMS", "500")),
        )
