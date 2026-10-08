#!/usr/bin/env python3
"""그래프 스키마 조회 API 가 두 백엔드에서 무엇을 돌려주는지 실측한다.

왜 이 스크립트가 있는가
-----------------------
온톨로지 모델을 그래프에 발행하려면 **인스턴스가 0건인 클래스**(가상 클래스)를 스키마
조회로 발견할 수 있어야 한다. 그런데 두 백엔드의 `db.labels()` 는 출처가 다르다.

    ontological-db : SELECT name FROM og_catalog.type   ← 선언된 카탈로그. 0건이어도 나온다.
    Neo4j          : 사용 중인 라벨                      ← 노드가 없으면 나오지 않는다(추정)

그 "추정"을 문서가 아니라 실측으로 확정하는 것이 이 스크립트다. 결과에 따라 발행 방식이
갈린다:

    분기 A — 제약/인덱스 선언만으로 라벨이 보인다  → 인스턴스 없이 발행 가능
    분기 B — 보이지 않는다                        → 클래스마다 앵커 노드가 필요

`inspect_catalog.py` 와 같은 자리에 있는 이유도 같다 — 서브모듈 하나가 아니라 플랫폼
계약을 검사한다.

사용법
------
    uv run --with neo4j python scripts/probe_graph_schema_api.py --uri bolt://localhost:7688
    uv run --with neo4j python scripts/probe_graph_schema_api.py --uri bolt://localhost:7687 \
        --user dev --password ''

이 스크립트는 **자기가 만든 것만 지운다.** 전역 삭제를 하지 않는다 (constitution IV).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# 프로브가 만드는 것들. 이름에 접두를 붙여 두면 실패로 남더라도 무엇이 쓰레기인지 알 수 있다.
PROBE_LABEL = "_ProbeVirtualClass"
PROBE_REL_TYPE = "_PROBE_REFERENCES"
PROBE_CONSTRAINT = "_probe_vc_key"
PROBE_INDEX = "_probe_vc_idx"


def load_root_env() -> dict[str, str]:
    """루트 .env 를 손으로 판다.

    python-dotenv 에 기대지 않는 이유는 `inspect_catalog.py` 와 같다 — 서브모듈이 없는
    맨 체크아웃에서도 돌아야 한다.
    """

    env: dict[str, str] = {}
    path = REPO_ROOT / ".env"
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _call(session, cypher: str):
    """한 건 실행하고 (행, 오류) 를 돌려준다. 미지원 프로시저도 결과의 일부다."""

    try:
        return [record.data() for record in session.run(cypher)], None
    except Exception as exc:  # noqa: BLE001 - 미지원 여부 자체가 관측 대상이다
        return None, f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"


def _labels(session) -> tuple[set[str] | None, str | None]:
    rows, err = _call(session, "CALL db.labels()")
    if rows is None:
        return None, err
    return {str(r.get("label")) for r in rows}, None


def _rel_types(session) -> tuple[set[str] | None, str | None]:
    rows, err = _call(session, "CALL db.relationshipTypes()")
    if rows is None:
        return None, err
    return {str(r.get("relationshipType")) for r in rows}, None


def _cleanup(session) -> None:
    """프로브가 만든 것만 제거한다."""

    for stmt in (
        f"DROP CONSTRAINT {PROBE_CONSTRAINT} IF EXISTS",
        f"DROP INDEX {PROBE_INDEX} IF EXISTS",
        f"MATCH (n:{PROBE_LABEL}) DETACH DELETE n",
    ):
        _call(session, stmt)


def probe(driver, database: str | None) -> dict:
    """제약만 선언한 라벨이 스키마 조회에 나타나는지 확인한다."""

    result: dict = {"steps": [], "errors": {}}
    kwargs = {"database": database} if database else {}

    with driver.session(**kwargs) as session:
        # 이전 실행이 남긴 것이 있으면 먼저 치운다 — 그래야 "이미 있었다"와 구분된다.
        _cleanup(session)

        baseline_labels, err = _labels(session)
        if baseline_labels is None:
            result["errors"]["db.labels"] = err
            baseline_labels = set()
        result["baseline_label_count"] = len(baseline_labels)
        result["baseline_has_probe_label"] = PROBE_LABEL in baseline_labels

        # --- 1. 노드 없이 제약 + 인덱스만 선언한다 -------------------------------
        _, c_err = _call(
            session,
            f"CREATE CONSTRAINT {PROBE_CONSTRAINT} IF NOT EXISTS "
            f"FOR (n:{PROBE_LABEL}) REQUIRE n.probe_key IS UNIQUE",
        )
        _, i_err = _call(
            session,
            f"CREATE INDEX {PROBE_INDEX} IF NOT EXISTS "
            f"FOR (n:{PROBE_LABEL}) ON (n.probe_at)",
        )
        result["constraint_supported"] = c_err is None
        result["index_supported"] = i_err is None
        if c_err:
            result["errors"]["create_constraint"] = c_err
        if i_err:
            result["errors"]["create_index"] = i_err

        labels_after_ddl, err = _labels(session)
        result["label_visible_after_ddl"] = (
            None if labels_after_ddl is None else PROBE_LABEL in labels_after_ddl
        )
        if err:
            result["errors"]["db.labels_after_ddl"] = err

        # SHOW CONSTRAINTS / SHOW INDEXES 는 최소한의 대안 경로다.
        rows, err = _call(session, "SHOW CONSTRAINTS")
        result["show_constraints_supported"] = rows is not None
        result["label_in_show_constraints"] = (
            None if rows is None else any(PROBE_LABEL in str(r) for r in rows)
        )
        if err:
            result["errors"]["SHOW CONSTRAINTS"] = err

        rows, err = _call(session, "SHOW INDEXES")
        result["show_indexes_supported"] = rows is not None
        result["label_in_show_indexes"] = (
            None if rows is None else any(PROBE_LABEL in str(r) for r in rows)
        )
        if err:
            result["errors"]["SHOW INDEXES"] = err

        rows, err = _call(session, "CALL db.schema.visualization()")
        result["schema_visualization_supported"] = rows is not None
        result["label_in_schema_visualization"] = (
            None if rows is None else any(PROBE_LABEL in str(r) for r in rows)
        )
        if err:
            result["errors"]["db.schema.visualization"] = err

        rows, err = _call(session, "CALL apoc.meta.schema()")
        result["apoc_meta_schema_supported"] = rows is not None
        result["label_in_apoc_meta_schema"] = (
            None if rows is None else any(PROBE_LABEL in str(r) for r in rows)
        )
        if err:
            result["errors"]["apoc.meta.schema"] = err

        rows, err = _call(session, "CALL db.propertyKeys()")
        result["property_keys_supported"] = rows is not None
        if rows is not None:
            keys = {str(r.get("propertyKey")) for r in rows}
            # 노드가 없어도 제약이 참조한 속성 키 토큰이 생기는가?
            result["probe_property_key_visible"] = "probe_key" in keys
        if err:
            result["errors"]["db.propertyKeys"] = err

        # --- 2. 앵커 노드를 하나 만들면 어떻게 달라지는가 ------------------------
        _, err = _call(
            session,
            f"MERGE (n:{PROBE_LABEL} {{probe_key: 'anchor'}}) SET n.probe_at = 1",
        )
        if err:
            result["errors"]["create_anchor"] = err

        labels_with_anchor, _ = _labels(session)
        result["label_visible_with_anchor"] = (
            None if labels_with_anchor is None else PROBE_LABEL in labels_with_anchor
        )

        # 관계 타입도 같은 질문이 있다 — 인스턴스 없이 선언할 방법이 있는가?
        rel_baseline, _ = _rel_types(session)
        result["rel_type_visible_without_instance"] = (
            None if rel_baseline is None else PROBE_REL_TYPE in rel_baseline
        )

        _cleanup(session)

        labels_after_cleanup, _ = _labels(session)
        # 노드를 지운 뒤에도 라벨 토큰이 남는지 — Neo4j 의 알려진 특성 확인
        result["label_lingers_after_delete"] = (
            None if labels_after_cleanup is None else PROBE_LABEL in labels_after_cleanup
        )

    return result


def verdict(result: dict) -> str:
    if result.get("label_visible_after_ddl") is True:
        return "A"
    if result.get("label_visible_with_anchor") is True:
        return "B"
    return "?"


def render(name: str, uri: str, result: dict) -> str:
    def mark(value) -> str:
        if value is True:
            return "예"
        if value is False:
            return "아니오"
        return "미지원/불가"

    lines = [
        f"## {name}  ({uri})",
        "",
        "| 관측 | 결과 |",
        "|---|---|",
        f"| 제약 생성 지원 | {mark(result.get('constraint_supported'))} |",
        f"| 인덱스 생성 지원 | {mark(result.get('index_supported'))} |",
        f"| **제약만으로 `db.labels()` 에 라벨 노출** | **{mark(result.get('label_visible_after_ddl'))}** |",
        f"| 앵커 노드 1개 만들면 노출 | {mark(result.get('label_visible_with_anchor'))} |",
        f"| `SHOW CONSTRAINTS` 에 노출 | {mark(result.get('label_in_show_constraints'))} |",
        f"| `SHOW INDEXES` 에 노출 | {mark(result.get('label_in_show_indexes'))} |",
        f"| `db.schema.visualization()` 지원 | {mark(result.get('schema_visualization_supported'))} |",
        f"| `db.schema.visualization()` 에 노출 | {mark(result.get('label_in_schema_visualization'))} |",
        f"| `apoc.meta.schema()` 지원 | {mark(result.get('apoc_meta_schema_supported'))} |",
        f"| `apoc.meta.schema()` 에 노출 | {mark(result.get('label_in_apoc_meta_schema'))} |",
        f"| `db.propertyKeys()` 지원 | {mark(result.get('property_keys_supported'))} |",
        f"| 제약이 참조한 속성 키 노출 | {mark(result.get('probe_property_key_visible'))} |",
        f"| 노드 삭제 후 라벨 잔존 | {mark(result.get('label_lingers_after_delete'))} |",
        "",
        f"**판정: 분기 {verdict(result)}**"
        + ("  — 인스턴스 없이 발행 가능" if verdict(result) == "A" else "")
        + ("  — 앵커 노드 필요" if verdict(result) == "B" else ""),
        "",
    ]
    if result.get("errors"):
        lines.append("<details><summary>오류/미지원 상세</summary>")
        lines.append("")
        for key, value in result["errors"].items():
            lines.append(f"- `{key}` — {value}")
        lines.append("")
        lines.append("</details>")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    env = load_root_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", default=env.get("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--user", default=env.get("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=env.get("NEO4J_PASSWORD", ""))
    parser.add_argument("--database", default=None)
    parser.add_argument("--name", default=None, help="표에 쓸 백엔드 이름")
    args = parser.parse_args()

    from neo4j import GraphDatabase

    name = args.name or ("ontological-db" if ":7687" in args.uri and args.user != "neo4j" else "Neo4j")

    try:
        driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
        driver.verify_connectivity()
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {args.uri} 에 접속할 수 없습니다: {exc}", file=sys.stderr)
        return 2

    try:
        result = probe(driver, args.database)
    finally:
        driver.close()

    print(render(name, args.uri, result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
