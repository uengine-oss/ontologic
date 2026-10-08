#!/usr/bin/env python
"""Board 가 의존하는 MCP 계약을 **코드로** 확인한다.

`scripts/agentic_rag_session.py` 와 같은 자리에 있지만 하는 일이 다르다. 저쪽은 LLM 에게
도구를 쥐여 주고 스스로 순서를 밟는지 본다. 여기는 **LLM 을 부르지 않는다** — 애플리케이션이
할 호출을 그대로 하고, 돌아온 것이 계약대로인지 단언한다.

계약이 어긋나면 기능이 조용히 틀린다. 특히 `graph://schema` 에 타입이 생기거나 행 상한이
바뀌면 위젯 매핑의 전제가 무너지는데, 증상은 "차트가 이상하다" 라서 원인을 짚기 어렵다.

    uv run python scripts/probe_board_mcp.py
    uv run python scripts/probe_board_mcp.py --url http://127.0.0.1:8100/mcp --out demo/board-probe
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ontology-studio"))

from backend.src.modules.board.mcp_client import BoardMcpClient  # noqa: E402
from backend.src.modules.board.settings import BoardSettings, normalize_mcp_url  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
_results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((PASS if ok else FAIL, name, detail))
    mark = "\033[32m PASS \033[0m" if ok else "\033[31m FAIL \033[0m"
    print(f"[{mark}] {name}" + (f"\n         {detail}" if detail else ""))
    return ok


async def run(url: str, out_dir: Path, cls_mat: str, cls_virt: str, cls_many: str) -> int:
    settings = BoardSettings(transport="http", url=normalize_mcp_url(url), command=[],
                             sample_limit=50, request_timeout=60)
    client = BoardMcpClient(settings)
    out_dir.mkdir(parents=True, exist_ok=True)

    def dump(name: str, payload) -> None:
        (out_dir / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    async with client.session() as s:
        names = await s.tool_names()
        dump("00-tools", names)
        check("도구 목록에 하이브리드 4종이 있다 (확장 플래그 ON)",
              {"ontology_resolve_entity", "ontology_graph_cypher",
               "ontology_get_datasource_schema", "ontology_query_datasource_sql"} <= set(names),
              f"{len(names)}개: {', '.join(names)}")

        # ── 1. graph://schema — 지도에 타입이 없다는 것이 AD-4 의 근거다
        schema = await s.read_resource("graph://schema")
        dump("01-graph-schema", schema)
        classes = schema.get("classes") or []
        check("graph://schema 가 클래스를 준다", bool(classes),
              f"클래스 {len(classes)}개 · 가상 {schema.get('counts',{}).get('virtual_classes')}개")

        mat = next((c for c in classes if c["class_name"] == cls_mat), None)
        check(f"{cls_mat} 엔트리에 property_names 가 있다", bool(mat and mat.get("property_names")),
              f"{len(mat.get('property_names') or []) if mat else 0}개")
        check("클래스 엔트리에 **타입이 없다** (AD-4 의 전제)",
              bool(mat) and "properties" not in mat and not any(
                  isinstance(p, dict) for p in (mat.get("property_names") or [])),
              "property_names 는 문자열 배열이다. 타입이 생기면 AD-4 를 재검토해야 한다")
        check("published_at 이 있다 (프로파일 캐시 키)",
              all("published_at" in m for m in (schema.get("models") or [])),
              str([m.get("published_at") for m in (schema.get("models") or [])]))

        # ── 2. JIT 스키마는 가상 클래스 전용이다
        rej = await s.call("ontology_get_datasource_schema", class_name=cls_mat)
        dump("02-jit-materialized-rejected", rej)
        check(f"ontology_get_datasource_schema({cls_mat}) 가 거절한다 (materialized)",
              bool(rej.get("error")), str(rej.get("error"))[:110])

        jit = await s.call("ontology_get_datasource_schema", class_name=cls_virt)
        dump("03-jit-virtual", jit)
        cols = jit.get("columns") or []
        check(f"ontology_get_datasource_schema({cls_virt}) 가 타입을 준다",
              bool(cols) and all("type" in c for c in cols),
              f"컬럼 {len(cols)}개 · 예: {cols[0] if cols else None}")

        # ── 3. _datasource_refs 는 응답 최상단에 붙는다
        whole = await s.call("ontology_graph_cypher",
                             query=f"MATCH (n:_Entity:{cls_mat}) RETURN n LIMIT 2")
        dump("04-cypher-whole-node", whole)
        keys = list((whole.get("rows") or [{}])[0].get("n", {}).keys())
        check("노드를 통째로 RETURN 하면 속성이 전부 온다 (값 추론의 재료)",
              len(keys) > 0, f"{len(keys)}개: {', '.join(sorted(keys)[:6])}…")
        refs = whole.get("_datasource_refs") or []
        check("_datasource_refs 가 응답 최상단에 붙는다",
              bool(refs) and all(r.get("join_on") for r in refs),
              f"{len(refs)}건 · 예: {refs[0].get('class')} join_on={refs[0].get('join_on')}" if refs else "")

        # ── 4. 행 예산 — 이 기능의 핵심 제약
        total = await s.call("ontology_graph_cypher",
                             query=f"MATCH (n:_Entity:{cls_many}) RETURN count(n) AS c")
        n_total = (total.get("rows") or [{}])[0].get("c")
        rows = await s.call("ontology_graph_cypher",
                            query=f"MATCH (n:_Entity:{cls_many}) RETURN n.product_id AS pid")
        dump("05-row-budget", {"count": total, "rows": rows})
        n_got = len(rows.get("rows") or [])
        check(f"Cypher 경로가 잘린다 ({cls_many}: 총 {n_total} → {n_got}행)",
              n_total is not None and n_got < n_total and rows.get("truncated") is True,
              f"truncated={rows.get('truncated')} · row_count={rows.get('row_count')} "
              f"← **참값이 아니다**")
        check("count() 는 상한과 무관하다 (총계를 아는 유일한 경로)",
              isinstance(n_total, int) and n_total > n_got, f"count={n_total}")

        # ── 5. Cypher 게이트
        blocked = await s.call("ontology_graph_cypher", query="MATCH (n:Table) RETURN n LIMIT 1")
        check("차단 라벨(:Table) 을 거부한다", bool(blocked.get("error")),
              str(blocked.get("error"))[:90])
        bypass = await s.call("ontology_graph_cypher",
                              query="MATCH (n) WHERE 'DataSource' IN labels(n) RETURN n LIMIT 1")
        check("문자열 우회('DataSource' IN labels) 도 거부한다", bool(bypass.get("error")),
              str(bypass.get("error"))[:90])
        called = await s.call("ontology_graph_cypher",
                              query="CALL db.labels() YIELD label RETURN label")
        check("CALL 을 거부한다 (생성 Cypher 에 쓰면 안 된다)", bool(called.get("error")),
              str(called.get("error"))[:90])
        dump("06-gate", {"blocked": blocked, "bypass": bypass, "call": called})

    failed = [r for r in _results if r[0] == FAIL]
    print(f"\n{'─'*66}\n{len(_results)-len(failed)}/{len(_results)} 통과 · 원문: {out_dir}")
    if failed:
        print("\n실패:")
        for _, name, detail in failed:
            print(f"  · {name}\n    {detail}")
    return 1 if failed else 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default=os.environ.get("BOARD_MCP_URL", "http://127.0.0.1:8100/mcp"))
    p.add_argument("--out", default=str(ROOT / "demo" / "board-probe"))
    p.add_argument("--materialized", default="MfgProduct")
    p.add_argument("--virtual", default="MfgDailyEquipment")
    p.add_argument("--many", default="MfgProductBom")
    a = p.parse_args()
    return asyncio.run(run(a.url, Path(a.out), a.materialized, a.virtual, a.many))


if __name__ == "__main__":
    raise SystemExit(main())
