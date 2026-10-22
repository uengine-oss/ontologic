"""저장소 — SQLAlchemy 2 Core. SQLite(기본) 와 PostgreSQL(psycopg) 둘 다에서 돈다.

JSON 값은 이식성을 위해 TEXT 에 직렬화한다. 시각은 RFC3339(UTC) 문자열.
이미 있는 DB 는 시작할 때 빠진 컬럼만 `ALTER TABLE … ADD COLUMN` 으로 더한다 (데이터 보존).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    insert,
    inspect,
    text,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError

metadata = MetaData()

systems = Table(
    "kinetic_systems", metadata,
    Column("name", String(100), primary_key=True),
    Column("base_url", Text, nullable=False),
    Column("openapi", Text, nullable=False),
    Column("auth_kind", String(40), nullable=False),
    Column("auth_header", String(100)),
    Column("auth_secret_env", String(100)),
    Column("timeout_ms", Integer, nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("description", Text),
    Column("openapi_url", Text),
    Column("health_path", String(200)),
    Column("manual_ops", Text),  # 수동 등록 Operation 목록 JSON (OpenAPI 새로고침과 무관하게 유지)
    Column("updated_at", String(40)),
    # 계약 §8 — 시스템 등록 모델 (API 관리 도구 공통 항목). JSON 값은 TEXT.
    Column("display_name", Text),
    Column("owner_team", Text),
    Column("contact", Text),
    Column("tags", Text),             # JSON 배열
    Column("icon", String(40)),
    Column("protocol", String(20)),   # 비면 'rest'
    Column("spec_format", String(20)),
    Column("spec_text", Text),        # openapi 로 바꾸지 못하는 원문(wsdl·sdl·proto·$metadata) 보관
    Column("environments", Text),     # JSON [{name, base_url}]
    Column("active_environment", String(100)),
    Column("retries", Integer),
    Column("auth_query_param", String(100)),
    Column("auth_token_url", Text),
    Column("auth_client_id", String(200)),
    Column("auth_client_secret_env", String(100)),
    Column("auth_scopes", Text),      # JSON 배열
    # 계약 §9.1 — login_token 설정 JSON {login_body, username_field, username_env, password_field, password_env,
    # token_path, scheme, ttl_seconds} (token_url 은 auth_token_url, header 는 auth_header). 비밀 값 없음.
    Column("auth_login", Text),
)
_ADDED = {"kinetic_systems": (
    "description", "openapi_url", "health_path", "manual_ops", "updated_at",
    "display_name", "owner_team", "contact", "tags", "icon", "protocol", "spec_format", "spec_text", "environments",
    "active_environment", "retries", "auth_query_param", "auth_token_url", "auth_client_id", "auth_client_secret_env",
    "auth_scopes", "auth_login")}
# 넓힌 컬럼 (PostgreSQL 만 — SQLite 는 길이를 강제하지 않는다)
_WIDENED = {"kinetic_systems": {"auth_kind": 40}}

plans = Table(
    "kinetic_plans", metadata,
    Column("id", String(40), primary_key=True),
    Column("doc", Text, nullable=False),
    Column("status", String(30), nullable=False),
    Column("actor_sub", String(200), nullable=False),
    Column("created_at", String(40), nullable=False),
)

runs = Table(
    "kinetic_runs", metadata,
    Column("id", String(40), primary_key=True),
    Column("plan_id", String(40), nullable=False, unique=True),  # 같은 plan 재실행 = 같은 run
    Column("doc", Text, nullable=False),
    Column("calls", Text, nullable=False),
    Column("status", String(20), nullable=False),
)

audit = Table(
    "kinetic_audit", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts", String(40), nullable=False),
    Column("event", String(40), nullable=False),
    Column("actor_sub", String(200)),
    Column("request_id", String(80)),
    Column("plan_id", String(40)),
    Column("run_id", String(40)),
    Column("detail", Text),
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def now_ms() -> str:
    """밀리초까지 — 보상 호출 순서처럼 같은 초 안의 순서를 보여야 할 때."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _normalize_url(url: str) -> str:
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.split("://", 1)[1]
    return url


class Store:
    def __init__(self, db_url: str):
        url = _normalize_url(db_url)
        kwargs: dict[str, Any] = {"future": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        self.engine = create_engine(url, **kwargs)
        metadata.create_all(self.engine)
        self._migrate()

    def _migrate(self) -> None:
        insp = inspect(self.engine)
        for table, cols in _ADDED.items():
            have = {c["name"] for c in insp.get_columns(table)}
            t = metadata.tables[table]
            with self.engine.begin() as c:
                for name in cols:
                    if name not in have:
                        ddl = t.c[name].type.compile(dialect=self.engine.dialect)
                        c.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))
        if self.engine.dialect.name == "postgresql":
            for table, cols in _WIDENED.items():
                lengths = {c["name"]: getattr(c["type"], "length", None) for c in insp.get_columns(table)}
                with self.engine.begin() as c:
                    for name, length in cols.items():
                        if lengths.get(name) is not None and lengths[name] < length:
                            c.execute(text(f"ALTER TABLE {table} ALTER COLUMN {name} TYPE VARCHAR({length})"))

    # ── systems ──
    def upsert_system(self, row: dict) -> None:
        with self.engine.begin() as c:
            if c.execute(select(systems.c.name).where(systems.c.name == row["name"])).first():
                c.execute(update(systems).where(systems.c.name == row["name"]).values(**row))
            else:
                c.execute(insert(systems).values(**row))

    def list_systems(self) -> list[dict]:
        with self.engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(select(systems).order_by(systems.c.name))]

    def delete_system(self, name: str) -> bool:
        with self.engine.begin() as c:
            return c.execute(systems.delete().where(systems.c.name == name)).rowcount > 0

    def get_system(self, name: str) -> dict | None:
        with self.engine.connect() as c:
            r = c.execute(select(systems).where(systems.c.name == name)).first()
            return dict(r._mapping) if r else None

    # ── plans ──
    def save_plan(self, plan: dict, *, new: bool = False) -> None:
        values = {"doc": json.dumps(plan, ensure_ascii=False), "status": plan["status"]}
        with self.engine.begin() as c:
            if new:
                c.execute(insert(plans).values(id=plan["id"], actor_sub=plan["actor_sub"],
                                               created_at=plan["created_at"], **values))
            else:
                c.execute(update(plans).where(plans.c.id == plan["id"]).values(**values))

    def get_plan(self, plan_id: str) -> dict | None:
        with self.engine.connect() as c:
            r = c.execute(select(plans.c.doc).where(plans.c.id == plan_id)).first()
            return json.loads(r[0]) if r else None

    # ── runs ──
    def create_run(self, run: dict, calls: dict) -> bool:
        """plan 당 run 하나. 이미 있으면 False (동시 실행 경합 방지)."""
        try:
            with self.engine.begin() as c:
                c.execute(insert(runs).values(id=run["id"], plan_id=run["plan_id"], status=run["status"],
                                              doc=json.dumps(run, ensure_ascii=False),
                                              calls=json.dumps(calls, ensure_ascii=False)))
            return True
        except IntegrityError:
            return False

    def save_run(self, run: dict) -> None:
        with self.engine.begin() as c:
            c.execute(update(runs).where(runs.c.id == run["id"]).values(
                doc=json.dumps(run, ensure_ascii=False), status=run["status"]))

    def get_run(self, run_id: str) -> dict | None:
        with self.engine.connect() as c:
            r = c.execute(select(runs.c.doc).where(runs.c.id == run_id)).first()
            return json.loads(r[0]) if r else None

    def list_runs(self) -> list[dict]:
        with self.engine.connect() as c:
            return [json.loads(r[0]) for r in c.execute(select(runs.c.doc))]

    def get_run_by_plan(self, plan_id: str) -> dict | None:
        with self.engine.connect() as c:
            r = c.execute(select(runs.c.doc).where(runs.c.plan_id == plan_id)).first()
            return json.loads(r[0]) if r else None

    def get_run_calls(self, run_id: str) -> dict:
        with self.engine.connect() as c:
            r = c.execute(select(runs.c.calls).where(runs.c.id == run_id)).first()
            return json.loads(r[0]) if r else {}

    # ── audit ──
    def audit(self, event: str, *, actor_sub: str | None, request_id: str | None,
              plan_id: str | None = None, run_id: str | None = None, detail: Any = None) -> None:
        with self.engine.begin() as c:
            c.execute(insert(audit).values(
                ts=now_iso(), event=event, actor_sub=actor_sub, request_id=request_id,
                plan_id=plan_id, run_id=run_id,
                detail=json.dumps(detail, ensure_ascii=False, default=str) if detail is not None else None))

    def list_audit(self, plan_id: str | None = None) -> list[dict]:
        q = select(audit).order_by(audit.c.id)
        if plan_id:
            q = q.where(audit.c.plan_id == plan_id)
        with self.engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(q)]
