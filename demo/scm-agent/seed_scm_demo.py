#!/usr/bin/env python3
"""하이브리드 agentic RAG 시나리오를 시드한다 — 그래프 토폴로지 + 데이터소스 시계열.

무엇을 만드는가
---------------
`manufacturing` 데이터소스의 13개 테이블을 두 갈래로 나눈다.

    마스터 (제품·원자재·공정·BOM·라우팅)  → materialized 클래스 + 그래프 인스턴스
    일별   (설비·품질·공정지표 …)          → virtual 클래스 (인스턴스 0건)

이 분할이 시나리오의 요점이다. 토폴로지는 그래프에 두고 대용량 시계열은 RDB 에 남겨,
질의 시점에 **그래프로 대상을 좁힌 뒤 SQL 로 집계**하게 한다. 시계열을 그래프 노드로
펼치면 토큰과 저장소가 함께 터진다.

골든 퀘스천: "제품 P001 의 라우팅에 포함된 공정 중 가동률이 가장 낮았던 설비와 그 일자는?"

선행 조건
---------
- data-fabric 이 `manufacturing` 을 등록하고 메타데이터를 추출해 두었을 것
  (`POST /api/datasources/manufacturing/extract-metadata-sync`)
- 마스터 인스턴스 적재에는 neo4j-text2sql(:8020)이 필요하다 — 이 스크립트는 소스 DB 에
  직접 붙지 않는다. 자격증명은 실행 서비스가 갖는다 (constitution 원칙 I·V).

전역 삭제를 하지 않는다. 자기가 만든 스키마 그룹만 다룬다 (constitution IV).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STUDIO = REPO_ROOT / "ontology-studio"
sys.path.insert(0, str(STUDIO))

SCHEMA_GROUP = "공급망 멀티에이전트"
DATASOURCE = "supplychain"
SOURCE_SCHEMA = "supplychain"

#: 그래프에 인스턴스로 올릴 마스터. 행 수가 작고 잘 변하지 않는다 — 토폴로지의 뼈대다.
MASTER_TABLES = [
    "scm_supplier",
    "scm_item",
    "scm_customer",
    "scm_contract",
    "scm_purchase_order",
]

#: 데이터소스에 남길 일별 시계열. `mfg_daily_equipment` 만 해도 3,500행이 넘는다.
#:
#: `mfg_daily_material_cost` 가 특히 중요하다 — 원자재의 **공급처·리드타임·단가·재고**가
#: 여기 있다. 그래서 "BOM 을 그래프로 펼친 뒤 각 부품의 공급 정보를 데이터소스에서 찾아
#: 조달 계획을 세운다"가 성립한다. 부품 목록은 그래프가, 공급 실적은 RDB 가 답한다.
DAILY_TABLES = [
    "scm_po_line",
    "scm_shipment",
    "scm_customs_declaration",
    "scm_inventory_daily",
    "scm_customer_order",
    "scm_claim_ticket",
]


def _class_name(table: str) -> str:
    from backend.src.modules.ontology.schema_ontology import to_class_name

    return to_class_name(table)


def preflight(datasource: str) -> str | None:
    """카탈로그가 이 데이터소스로 테이블을 찾을 수 있는지 미리 본다.

    찾지 못하면 원인을 지목한다. `read_catalog` 은 `t.datasource` / `t.db` 속성으로
    거르는데, `:Table` 의 MERGE 키가 `(name, schema)` 2-튜플이라 **서로 다른 DB 에 같은
    `schema.table` 이 있으면 한 노드로 합쳐지고** 속성은 마지막에 쓴 쪽이 이긴다
    (docs/catalog-schema.md "알려진 위험"). 그러면 관계로는 닿는데 속성으로는 안 닿는
    상태가 되고, 증상은 "카탈로그에 테이블이 없습니다"라서 원인을 짚기 어렵다.
    """

    from backend.src.modules.ontology.tools import get_driver, session_kwargs

    with get_driver().session(**session_kwargs()) as session:
        by_property = session.run(
            "MATCH (t:Table) WHERE (t.datasource = $ds OR t.db = $ds) AND t.schema = $schema "
            "RETURN count(t) AS c",
            {"ds": datasource, "schema": SOURCE_SCHEMA},
        ).single()["c"]
        by_relationship = session.run(
            "MATCH (d:DataSource {name: $ds})-[:HAS_SCHEMA]->(s:Schema {name: $schema})"
            "-[:HAS_TABLE]->(t:Table) RETURN count(t) AS c, collect(DISTINCT t.datasource) AS owners",
            {"ds": datasource, "schema": SOURCE_SCHEMA},
        ).single()

    if by_property:
        return None

    if by_relationship["c"]:
        owners = [o for o in by_relationship["owners"] if o]
        return (
            f"'{datasource}' 는 관계로는 테이블 {by_relationship['c']}개에 닿지만 "
            f"`Table.datasource` 속성은 {owners} 로 되어 있어 카탈로그 조회가 실패합니다.\n"
            f"   원인: :Table 의 MERGE 키가 (name, schema) 라서 같은 "
            f"'{SOURCE_SCHEMA}.*' 를 가진 다른 데이터소스와 노드가 합쳐졌습니다.\n"
            f"   (docs/catalog-schema.md '알려진 위험: Table MERGE 키가 제약보다 좁다')\n"
            f"   해결: (a) data-fabric 에서 '{datasource}' 메타데이터를 다시 추출하거나,\n"
            f"        (b) 같은 물리 DB 를 가리킨다면 --datasource {owners[0] if owners else '<owner>'} 로 실행"
        )

    return (
        f"카탈로그에 '{datasource}' / '{SOURCE_SCHEMA}' 테이블이 없습니다.\n"
        f"   data-fabric 에서 메타데이터 추출을 먼저 실행하세요:\n"
        f"   POST /api/datasources/{datasource}/extract-metadata-sync"
    )


def generate_classes(datasource: str, dry_run: bool = False) -> dict:
    """카탈로그에서 클래스를 만든다 — 결정적이며 LLM 을 부르지 않는다.

    두 번에 나눠 부르되 **첫 번째는 전체 테이블**을 대상으로 한다. `generate()` 는 인자로
    받은 테이블 **사이의** 외래키만 관계로 만들기 때문이다. 마스터와 일별을 따로 부르면
    `mfg_daily_equipment.step_id → mfg_process_step` 처럼 두 묶음을 **가로지르는** FK 가
    양쪽 모두에서 빠지고, 그러면 그래프 결과에서 데이터소스로 건너갈 단서
    (`_datasource_refs`)가 만들어지지 않는다 — 시나리오의 핵심이 조용히 사라진다.

    두 번째 호출이 일별 테이블만 다시 바인딩해 virtual 로 바꾼다.
    """

    from backend.src.modules.ontology import schema_ontology

    structure = schema_ontology.generate(
        datasource, SOURCE_SCHEMA, schema_group=SCHEMA_GROUP,
        tables=MASTER_TABLES + DAILY_TABLES, bind=False, dry_run=dry_run,
    )
    daily = schema_ontology.generate(
        datasource, SOURCE_SCHEMA, schema_group=SCHEMA_GROUP,
        tables=DAILY_TABLES, bind=True, dry_run=dry_run,
    )
    return {"structure(all)": structure, "daily(bind)": daily}


def ingest_masters(limit: int = 500) -> dict:
    """마스터 테이블의 행을 그래프 인스턴스로 올린다.

    SQL 실행은 text2sql 이 한다 — 이 스크립트는 데이터소스 자격증명을 갖지 않는다.
    """

    from backend.src.modules.ontology import datasource_exec
    from backend.src.modules.ontology.tools import get_driver, session_kwargs

    report: dict[str, int | str] = {}
    driver = get_driver()

    for table in MASTER_TABLES:
        klass = _class_name(table)
        outcome = datasource_exec.run_direct_sql(
            f"SELECT * FROM {SOURCE_SCHEMA}.{table} LIMIT {limit}", DATASOURCE
        )
        if outcome.get("status") != "ok":
            report[table] = f"실패: {outcome.get('error')}"
            continue

        rows = outcome["rows"]
        with driver.session(**session_kwargs()) as session:
            # 다시 시드할 때 쌓이지 않도록 이 클래스의 인스턴스만 먼저 지운다.
            session.run(f"MATCH (n:_Entity:`{klass}`) DETACH DELETE n")
            for row in rows:
                clean = {
                    key: (value if isinstance(value, (str, int, float, bool)) else str(value))
                    for key, value in row.items()
                    if value is not None
                }
                session.run(
                    f"CREATE (n:_Entity:`{klass}`) SET n = $props", {"props": clean}
                )
        report[table] = len(rows)
    return report


def link_masters() -> dict:
    """외래키에 해당하는 인스턴스 관계를 잇는다.

    관계 **유형**은 `generate()` 가 이미 스키마에 만들었다. 여기서는 실제 인스턴스를
    잇는다 — 이것이 없으면 Cypher 로 제품→라우팅→공정을 따라갈 수 없다.
    """

    from backend.src.modules.ontology.tools import get_driver, session_kwargs

    links = [
        # (from_class, from_key, to_class, to_key, rel_type)
        ("ScmItem", "primary_supplier_id", "ScmSupplier", "supplier_id", "REFERENCES_SCM_SUPPLIER"),
        ("ScmItem", "alt_supplier_id", "ScmSupplier", "supplier_id", "ALT_SUPPLIED_BY"),
        ("ScmContract", "supplier_id", "ScmSupplier", "supplier_id", "REFERENCES_SCM_SUPPLIER"),
        ("ScmPurchaseOrder", "supplier_id", "ScmSupplier", "supplier_id", "REFERENCES_SCM_SUPPLIER"),
        ("ScmPurchaseOrder", "contract_id", "ScmContract", "contract_id", "REFERENCES_SCM_CONTRACT"),
    ]

    driver = get_driver()
    report: dict[str, int] = {}
    with driver.session(**session_kwargs()) as session:
        for from_class, from_key, to_class, to_key, rel in links:
            result = session.run(
                f"MATCH (a:_Entity:`{from_class}`), (b:_Entity:`{to_class}`) "
                f"WHERE a.`{from_key}` = b.`{to_key}` "
                f"MERGE (a)-[r:`{rel}`]->(b) RETURN count(r) AS c"
            )
            report[f"{from_class}-[{rel}]->{to_class}"] = result.single()["c"]
    return report


def add_behavior() -> dict:
    """골든 퀘스천을 커버하는 behavior 를 하나 심는다.

    behavior 가 있으면 에이전트가 SQL 을 직접 쓰지 않고도 답할 수 있다 — 빌드 시점에
    검증된 정의가 항상 우선이다.
    """

    from backend.src.modules.agent_session import session_store

    schema = session_store.get_schema_by_name(SCHEMA_GROUP)
    if not schema:
        return {"error": f"스키마 그룹 '{SCHEMA_GROUP}' 이 없습니다."}

    session_store.upsert_class_behavior(
        schema["id"], "ScmInventoryDaily", "cover_days_for_items",
        description="주어진 품목들의 최신 재고 스냅샷 합계와 커버일수(가용재고/일평균사용량)",
        parameters=[
            {"name": "item_ids", "type": "string_list", "required": True,
             "description": "대상 품목 ID 목록"},
        ],
        sql_template=(
            "SELECT item_id, snapshot_date, SUM(on_hand_qty) AS on_hand, SUM(reserved_qty) AS reserved, "
            "SUM(in_transit_qty) AS in_transit, SUM(avg_daily_usage) AS daily_usage, "
            "ROUND((SUM(on_hand_qty)-SUM(reserved_qty))/NULLIF(SUM(avg_daily_usage),0), 1) AS cover_days "
            f"FROM {SOURCE_SCHEMA}.scm_inventory_daily "
            "WHERE item_id IN ({{item_ids}}) AND snapshot_date = (SELECT MAX(snapshot_date) FROM "
            f"{SOURCE_SCHEMA}.scm_inventory_daily) "
            "GROUP BY item_id, snapshot_date ORDER BY cover_days ASC"
        ),
        output_columns=["item_id", "snapshot_date", "on_hand", "reserved", "in_transit", "daily_usage", "cover_days"],
        max_rows=50,
        golden_question="안전재고를 이탈한 품목의 재고 커버일수는?",
    )
    return {"behavior": "cover_days_for_items"}


def publish_model() -> dict:
    from backend.src.modules.agent_session import session_store
    from backend.src.modules.ontology import publish

    schema = session_store.get_schema_by_name(SCHEMA_GROUP)
    if not schema:
        return {"error": f"스키마 그룹 '{SCHEMA_GROUP}' 이 없습니다."}
    return publish.publish(schema["id"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="계획만 보고 쓰지 않는다")
    parser.add_argument("--skip-ingest", action="store_true",
                        help="마스터 적재를 건너뛴다 (text2sql 이 없을 때)")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument(
        "--datasource", default=DATASOURCE,
        help="카탈로그에서 테이블을 찾을 데이터소스 이름 (기본 manufacturing)",
    )
    args = parser.parse_args()

    print("0. 카탈로그 사전 점검")
    problem = preflight(args.datasource)
    if problem:
        print(f"   [FAIL] {problem}")
        return 1
    print(f"   '{args.datasource}' / '{SOURCE_SCHEMA}' 확인")

    print("\n1. 클래스 생성 (카탈로그 → 온톨로지, 결정적)")
    generated = generate_classes(args.datasource, dry_run=args.dry_run)
    for key, value in generated.items():
        if value.get("error"):
            print(f"   [FAIL] {key}: {value['error']}")
            return 1
        # dry_run 은 계획(classes/relationships)을, 실제 실행은 결과(created_*)를 준다.
        classes = value.get("created_classes") or value.get("classes") or []
        rels = value.get("created_relationships") or value.get("relationships") or []
        kind = value.get("binding_kind") or ("virtual" if "bind" in key else "materialized")
        print(f"   {key}: 클래스 {len(classes)}개, 관계 {len(rels)}개 ({kind})")

    if args.dry_run:
        print("\ndry-run 이므로 여기서 멈춥니다.")
        return 0

    if args.skip_ingest:
        print("\n2-3. 마스터 적재/연결 건너뜀 (--skip-ingest)")
    else:
        print("\n2. 마스터 인스턴스 적재 (text2sql 경유)")
        for table, count in ingest_masters(args.limit).items():
            print(f"   {table}: {count}")

        print("\n3. 인스턴스 관계 연결")
        for label, count in link_masters().items():
            print(f"   {label}: {count}")

    print("\n4. behavior 등록")
    print(f"   {add_behavior()}")

    print("\n5. 그래프에 발행")
    published = publish_model()
    if published.get("error"):
        print(f"   [FAIL] {published['error']}")
        return 1
    print(f"   {published['counts']}")
    print(f"   제약: {published['constraints_created']}")

    print("\n완료. MCP 를 띄워 확인하세요:")
    print("   MCP_TRANSPORT=http MCP_PORT=8100 MCP_ALLOW_DATASOURCE_EXPANSION=true \\")
    print("     uv run python -m backend.src.modules.ontology_mcp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
