"""그래프 접근 추상화. 실행기는 이 인터페이스만 쓴다 — 테스트는 가짜를 넣는다."""

from __future__ import annotations

from typing import Any, Protocol

from .targeting import build_query, quote

CATALOG_CYPHER = (
    "MATCH (m:_OntologyModel)-[:HAS_CLASS]->(c:_OntologyClass)-[:HAS_ACTION]->"
    "(a:_OntologyBehavior {behavior_type:'action'}) "
    "RETURN a AS a, c.class_name AS class_name, m.schema_id AS schema_id"
)


class GraphReader(Protocol):
    async def load_actions(self) -> list[dict]:
        """발행된 액션 노드 속성 목록 (class_name·schema_id 보강)."""

    async def find(self, label: str, filters: list[dict], limit: int, *, classes, key_property: str | None = None,
                   ids: list[str] | None = None) -> list[tuple[str, dict]]:
        """(elementId, 속성) 목록."""

    async def set_property(self, label: str, key_property: str | None, key: str, prop: str, value: Any) -> None:
        ...


def _plain(v: Any) -> Any:
    """neo4j 시간 타입 등 JSON 으로 못 보내는 값을 문자열로."""
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    iso = getattr(v, "iso_format", None)
    return iso() if callable(iso) else str(v)


class Neo4jGraph:
    def __init__(self, uri: str, user: str, password: str, database: str | None = None):
        from neo4j import AsyncGraphDatabase

        self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        self.database = database

    def _session(self):
        return self.driver.session(**({"database": self.database} if self.database else {}))

    async def close(self) -> None:
        await self.driver.close()

    async def load_actions(self) -> list[dict]:
        async with self._session() as s:
            res = await s.run(CATALOG_CYPHER)
            out = []
            async for r in res:
                props = _plain(dict(r["a"]))
                props.setdefault("class_name", r["class_name"])
                props.setdefault("schema_id", r["schema_id"])
                out.append(props)
            return out

    async def find(self, label, filters, limit, *, classes, key_property=None, ids=None):
        cypher, params = build_query(label, filters, limit, classes=classes, key_property=key_property, ids=ids)
        async with self._session() as s:
            res = await s.run(cypher, params)
            return [(r["eid"], _plain(dict(r["n"]))) async for r in res]

    async def set_property(self, label, key_property, key, prop, value):
        match = f"toString(n.{quote(key_property)}) = $key" if key_property else "elementId(n) = $key"
        cypher = f"MATCH (n:{quote(label, '클래스')}) WHERE {match} SET n.{quote(prop)} = $value"
        async with self._session() as s:
            await (await s.run(cypher, {"key": str(key), "value": value})).consume()
