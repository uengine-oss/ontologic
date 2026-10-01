#!/usr/bin/env python3
"""spec 008 시나리오 채점 — 증강 전/후를 같은 척도로 잰다 (T3).

계약: ``specs/008-legacy-metadata-to-ontology/contracts/scoring-report.md``

## 왜 스크립트인가

SC-001~005 가 "측정 가능"해야 스펙이 성립한다. 증강은 LLM 에 의존해 결과가 결정적이지 않으므로
사람 눈으로 본 한 번의 관찰은 근거가 되지 않는다.

## 채점기를 다시 구현하지 않는다

바인딩 판정은 ontology-studio 의 ``entity_matcher`` 를 **그대로 불러다 쓴다.** 같은 계산을 두 벌
만들면 헌법 원칙 III 이 경고하는 divergence 가 생기고, 그러면 "채점기는 통과하는데 제품은 실패"
하거나 그 반대가 된다. 그 모듈은 표준 라이브러리만 쓰므로 서비스를 띄우지 않고 불러올 수 있다.

## 목표 개념은 정답지에서 만든다

전략1(역바인딩)은 **문서가 기술한 엔티티**를 테이블에 맞춘다. 이 시나리오의 "문서"에 해당하는
것이 정답지의 업무 의미 레이블이다 — 테이블 레이블이 엔티티 이름, 컬럼 레이블이 속성 이름.
즉 "사람이 업무 용어로 쓴 개념 목록"을 그대로 재현한다.

이렇게 하면 대조가 깨끗하다. 엔티티는 한글 업무어, 테이블·컬럼은 `TB01`·`C001` 이므로
**이름에서 얻을 신호가 정확히 0** 이고, 증강된 설명만이 둘을 이을 수 있다.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("pyyaml 이 필요합니다: uv run --with pyyaml --with neo4j python scripts/score_scenario.py ...")

REPO = Path(__file__).resolve().parent.parent
MATCHER_PATH = REPO / "ontology-studio/backend/src/modules/ontology/entity_matcher.py"


def load_matcher():
    """제품 코드의 채점기를 그대로 불러온다 (재구현 금지 — 모듈 docstring 참조)."""
    if not MATCHER_PATH.exists():
        sys.exit(f"채점기를 찾지 못했습니다: {MATCHER_PATH}")
    spec = importlib.util.spec_from_file_location("entity_matcher", MATCHER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def norm(s: str) -> str:
    """이름 비교는 대소문자를 무시한다.

    PostgreSQL 은 따옴표 없는 `TB01` 을 `tb01` 로 접는다 — 매핑은 `TB01` 인데 카탈로그에는
    `tb01` 로 들어온다(2026-08-05 실측). 이 정규화가 없으면 SC-002 가 **항상 0** 이 나오고,
    원인이 "증강 실패"로 오독되기 쉽다.
    """
    return (s or "").strip().lower()


# ── 카탈로그 읽기 ───────────────────────────────────────────────────────────

_CATALOG_QUERY = """
MATCH (t:Table)
WHERE (t.datasource = $ds OR t.db = $ds) AND toLower(t.schema) = toLower($schema)
OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column)
RETURN t.name AS name,
       coalesce(t.description, '') AS description,
       coalesce(t.description_source, '') AS description_source,
       collect({
         name: c.name,
         type: coalesce(c.type, c.dtype, ''),
         description: coalesce(c.description, ''),
         description_source: coalesce(c.description_source, ''),
         value_shape: coalesce(c.value_shape, '')
       }) AS columns
ORDER BY t.name
"""


def read_catalog(driver, database: str, ds: str, schema: str) -> dict:
    """카탈로그를 읽는다. 헌법 원칙 II·III 을 지킨다 — 데이터소스로 함께 거르고 두 표기를 받는다."""
    with driver.session(database=database) as s:
        rows = s.run(_CATALOG_QUERY, ds=ds, schema=schema).data()
    tables = []
    for r in rows:
        cols = [c for c in r["columns"] if c and c.get("name")]
        tables.append({
            "name": r["name"],
            "description": r["description"],
            # 근거 필드를 빠뜨리면 채워진 설명이 전부 "근거 없음"으로 집계된다 —
            # 실제로 그렇게 오탐했다(2026-08-05).
            "description_source": r["description_source"],
            "columns": cols,
        })
    return {"datasource": ds, "schema": schema, "tables": tables}


def datasource_count(driver, database: str) -> int:
    with driver.session(database=database) as s:
        return s.run("MATCH (d:DataSource) RETURN count(d) AS n").single()["n"]


def inferred_relations(driver, database: str, schema: str) -> list[dict]:
    # 증강은 추론 관계를 `(:Table)-[:FK_TO_TABLE {inferred: true}]->(:Table)` 로 쓴다
    # (skill_augment_step 의 `_UPSERT_INFERRED_REL` 주석 — 카탈로그 API 가 읽는 형태).
    # 예전 `INFERRED_REFERENCES` 만 보면 관계를 찾아도 늘 0 으로 채점된다.
    q = """
    MATCH (a:Table)-[r:FK_TO_TABLE]->(b:Table)
    WHERE r.inferred = true AND toLower(a.schema) = toLower($schema)
    RETURN a.name AS from_table, r.sourceColumn AS from_col,
           b.name AS to_table,  r.targetColumn AS to_col
    """
    with driver.session(database=database) as s:
        try:
            return s.run(q, schema=schema).data()
        except Exception:
            return []


# ── 목표 개념 ───────────────────────────────────────────────────────────────

def entities_from_mapping(doc: dict) -> list[dict]:
    """정답지의 업무 의미 레이블 → 전략1이 받는 엔티티 목록.

    `label` 이 빈 항목은 넣지 않는다 — 채점 기준이 없으므로 맞았는지 판정할 수 없다.
    빠진 수는 `excluded.no_label` 로 보고한다 (계약).
    """
    out, skipped = [], 0
    for t in doc["tables"]:
        if not t.get("label"):
            skipped += 1
            continue
        props = [{"name": c["label"], "type": ""} for c in t["columns"] if c.get("label")]
        skipped += sum(1 for c in t["columns"] if not c.get("label"))
        out.append({
            "class_name": t["label"],
            "properties": props,
            "_answer_table": t["target"],  # 정답. 채점에만 쓰고 매칭에는 넘기지 않는다.
        })
    return out, skipped


# ── 선행 검사 ───────────────────────────────────────────────────────────────

def check_mapping_hash(mapping_path: Path, artifacts: list[Path]) -> list[str]:
    """생성물의 해시 주석이 현재 매핑과 같은가.

    어긋난 채로 채점하면 **조용히 틀린 답**이 나온다 — 채점기는 매핑을 정답으로 믿는다.
    """
    digest = hashlib.sha256(mapping_path.read_bytes()).hexdigest()
    errs = []
    for p in artifacts:
        if not p.exists():
            errs.append(f"생성물 없음: {p}")
            continue
        head = p.read_text(encoding="utf-8", errors="replace")[:400]
        m = re.search(r"mapping-sha256:\s*([0-9a-f]{64})", head)
        if not m:
            errs.append(f"해시 주석 없음: {p.name}")
        elif m.group(1) != digest:
            errs.append(f"매핑과 생성물 불일치: {p.name} — 다시 생성하세요")
    return errs


def check_no_original_names(catalog: dict, doc: dict) -> list[str]:
    """카탈로그에 원본 이름이 남아 있으면 난독화에 구멍이 있다."""
    originals = {norm(t["source"]) for t in doc["tables"]}
    originals |= {norm(c["source"]) for t in doc["tables"] for c in t["columns"]}
    leaked = set()
    for t in catalog["tables"]:
        if norm(t["name"]) in originals:
            leaked.add(t["name"])
        for c in t["columns"]:
            if norm(c["name"]) in originals:
                leaked.add(f"{t['name']}.{c['name']}")
    return [f"카탈로그에 원본 이름이 남음: {sorted(leaked)[:8]}"] if leaked else []


# ── 채점 ────────────────────────────────────────────────────────────────────

def score(matcher, entities: list[dict], catalog: dict) -> dict:
    """실제 제품 채점기로 판정하고 정답지와 대조한다."""
    answer = {e["class_name"]: norm(e["_answer_table"]) for e in entities}
    payload = [{"class_name": e["class_name"], "properties": e["properties"]} for e in entities]
    result = matcher.match_all(payload, catalog)

    auto = correct = wrong = 0
    detail = []
    for m in result.get("matches", []):
        verdict = m.get("verdict")
        top = (m.get("candidates") or [{}])[0]
        picked = norm(top.get("table", ""))
        want = answer.get(m["entity"], "")
        row = {
            "entity": m["entity"],
            "verdict": verdict,
            "picked": top.get("table", ""),
            "expected": want,
            "score": round(float(top.get("score", 0.0)), 3),
        }
        if verdict == matcher.AUTO:
            auto += 1
            if picked == want:
                correct += 1
                row["ok"] = True
            else:
                wrong += 1
                row["ok"] = False
        detail.append(row)
    return {
        "auto_bindings": auto,
        "correct_bindings": correct,
        "wrong_bindings": wrong,
        "of": len(entities),
        "detail": detail,
    }


def fill_rates(catalog: dict) -> dict:
    t_all = len(catalog["tables"])
    t_filled = sum(1 for t in catalog["tables"] if t["description"].strip())
    cols = [c for t in catalog["tables"] for c in t["columns"]]
    c_filled = sum(1 for c in cols if (c.get("description") or "").strip())
    # 근거 없는 설명 = 추측 (FR-014). 계약상 0이어야 한다.
    no_ev = sum(
        1 for c in cols
        if (c.get("description") or "").strip() and not (c.get("description_source") or "").strip()
    )
    no_ev += sum(
        1 for t in catalog["tables"]
        if t["description"].strip() and not (t.get("description_source") or "").strip()
    )
    return {
        "tables": {"filled": t_filled, "of": t_all},
        "columns": {"filled": c_filled, "of": len(cols)},
        "without_evidence": no_ev,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="spec 008 시나리오 채점")
    ap.add_argument("--mapping", required=True, type=Path)
    ap.add_argument("--datasource", required=True)
    ap.add_argument("--schema", default="legacy")
    ap.add_argument("--phase", choices=["before", "after"], required=True)
    ap.add_argument("--neo4j-uri", default=None)
    ap.add_argument("--neo4j-user", default="neo4j")
    ap.add_argument("--neo4j-password", default=None)
    ap.add_argument("--neo4j-database", default="neo4j")
    ap.add_argument("--seed-dir", type=Path, default=None, help="해시 검사할 생성물 위치")
    ap.add_argument("--skip-preflight", action="store_true")
    args = ap.parse_args()

    from neo4j import GraphDatabase  # 지연 임포트 — 매핑 오류는 DB 없이도 보고한다

    doc = yaml.safe_load(args.mapping.read_text(encoding="utf-8"))
    matcher = load_matcher()

    failures: list[str] = []

    # ── 선행 검사 1: 매핑 해시 ──
    if args.seed_dir and not args.skip_preflight:
        failures += check_mapping_hash(
            args.mapping,
            [args.seed_dir / "05_ddl_legacy.sql", args.seed_dir / "06_dml_legacy.sql"],
        )

    uri = args.neo4j_uri or "bolt://127.0.0.1:7687"
    driver = GraphDatabase.driver(uri, auth=(args.neo4j_user, args.neo4j_password))

    ds_before = datasource_count(driver, args.neo4j_database)
    catalog = read_catalog(driver, args.neo4j_database, args.datasource, args.schema)

    if not catalog["tables"]:
        failures.append(
            f"카탈로그에 테이블이 없습니다 (datasource={args.datasource}, schema={args.schema}) "
            "— 메타데이터 추출을 먼저 실행하세요"
        )

    # ── 선행 검사 2: 난독화 완전성 ──
    if not args.skip_preflight:
        failures += check_no_original_names(catalog, doc)

    entities, no_label = entities_from_mapping(doc)
    scored = score(matcher, entities, catalog) if catalog["tables"] else {
        "auto_bindings": 0, "correct_bindings": 0, "wrong_bindings": 0,
        "of": len(entities), "detail": [],
    }
    fills = fill_rates(catalog)
    inferred = inferred_relations(driver, args.neo4j_database, args.schema)

    # ── 선행 검사 3: 데이터 보존 (FR-032 · SC-007) ──
    ds_after = datasource_count(driver, args.neo4j_database)
    if ds_after < ds_before:
        failures.append(f"채점 중 :DataSource 가 줄었습니다 ({ds_before} → {ds_after})")
    driver.close()

    removed_fk = doc.get("foreign_keys") or []
    fk_pairs = {
        (norm(fk["from"]["table"]), norm(fk["to"]["table"]))
        for fk in removed_fk if "from" in fk and "to" in fk
    }
    matched_fk = sum(
        1 for r in inferred
        if (norm(r.get("from_table", "")), norm(r.get("to_table", ""))) in fk_pairs
    )

    report = {
        "mapping_sha256": hashlib.sha256(args.mapping.read_bytes()).hexdigest(),
        "phase": args.phase,
        "datasource": args.datasource,
        "schema": args.schema,
        "sc_001_auto_bindings": scored["auto_bindings"],
        "sc_002_correct_bindings": {"n": scored["correct_bindings"], "of": scored["of"]},
        "sc_003_description_fill": fills,
        "sc_004_inferred_relations": {
            "found": len(inferred),
            "matching_removed_fk": matched_fk,
            "of_removed_fk": len(fk_pairs),
        },
        "sc_005_wrong_bindings": scored["wrong_bindings"],
        "excluded": {"no_label": no_label},
        "detail": scored["detail"],
    }

    # ── 엄격 기준 (계약) ──
    if args.phase == "before" and scored["auto_bindings"] != 0:
        failures.append(
            f"SC-001 위반: 증강 전인데 자동 바인딩이 {scored['auto_bindings']}건 "
            "— 난독화가 불완전합니다 (이름 신호가 0이면 총점이 0.2를 넘을 수 없음)"
        )
    if scored["wrong_bindings"] != 0:
        failures.append(f"SC-005 위반: 잘못된 자동 바인딩 {scored['wrong_bindings']}건")
    if fills["without_evidence"] != 0:
        failures.append(
            f"SC-003 위반: 근거 없는 설명 {fills['without_evidence']}건 (FR-014 — 추측 금지)"
        )

    report["failures"] = failures
    report["verdict"] = "FAIL" if failures else "PASS"

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("", file=sys.stderr)
    print(f"[{report['verdict']}] phase={args.phase}", file=sys.stderr)
    print(
        f"  자동 바인딩 {scored['auto_bindings']} · 정답 {scored['correct_bindings']}/{scored['of']}"
        f" · 오답 {scored['wrong_bindings']}",
        file=sys.stderr,
    )
    print(
        f"  설명 채움 테이블 {fills['tables']['filled']}/{fills['tables']['of']}"
        f" · 컬럼 {fills['columns']['filled']}/{fills['columns']['of']}",
        file=sys.stderr,
    )
    print(
        f"  추론 관계 {len(inferred)} (제거된 FK {len(fk_pairs)}건 중 {matched_fk} 일치)",
        file=sys.stderr,
    )
    for f in failures:
        print(f"  실패: {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
