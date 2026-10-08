#!/usr/bin/env python3
"""v3 의 1차 사전 시연 절을 **재구성 이후 실측**으로 교정한다 → v4.

왜 v2 를 다시 만들지 않는가
---------------------------
`update_proposal.py` 는 원본 초안에서 v2 를 만든다. 그런데 그 뒤로 v3 가 생겼고, 거기에는
2차 사전 시연(오케스트레이션·승인 게이트·이기종 4개 시스템)과 별첨9 가 들어 있다. v2 를 다시
찍으면 그 작업이 통째로 사라진다. **v3 를 입력으로 받아 필요한 자리만 고친다.**

무엇이 틀어져 있었나
--------------------
v3 안에서 두 절이 서로 다른 말을 한다.

  1차 시연 절 : "PostgreSQL 업무 DB" · "마스터 212건, 지식그래프" · "카탈로그에서 클래스 생성"
  2차 시연 절 : "이기종 4개 시스템"

1차 구성을 되돌린 뒤로 실측이 달라졌는데 그 절만 예전 값을 들고 있다. 평가위원이 두 절을
나란히 읽으면 바로 걸리는 모순이다. 고칠 것은 셋이다.

  A. 실행 조건표  — 문서 기반 구축 · 이기종 4개 시스템 · 그래프 복제 0건으로 교정
  B. 결과표       — 44회 → 52회, 도메인별 조회 시스템 열 추가
  C. 주석 한 줄   — 첫 구성을 왜 되돌렸는지 밝힌다 (숨기면 다음 사람이 같은 실수를 한다)
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import docx
from docx.shared import Pt

SRC = Path("/Users/uengine/연구과제/SCM/1. (필수) 사업계획서_AI에이전트기반_공급망관리_초안_v3.docx")
DST = SRC.with_name(SRC.stem.replace("_v3", "_v4") + ".docx")
RUNS = Path("/Users/uengine/ontologic/demo/scm-agent/runs")

BODY_FONT = "돋움"
TABLE_PT = 8

#: 도메인별 조회 시스템. 실행 로그의 `datasource_update` 이벤트에서 뽑는다.
SYSTEM_LABEL = {"scm_erp": "ERP", "scm_wms": "WMS", "scm_customs": "관세", "scm_crm": "CRM"}
ORDER = ["S1-procurement", "S2-customs", "S3-inventory",
         "S4-contract", "S5-purchasing", "S6-customer-support"]


def load_runs() -> dict[str, dict]:
    out = {}
    for f in RUNS.glob("S*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        systems = []
        for e in d["events"]:
            if e["event"] == "datasource_update":
                name = (e["data"] or {}).get("datasource") or ""
                if name and name not in systems:
                    systems.append(name)
        d["systems"] = [SYSTEM_LABEL.get(s, s) for s in sorted(systems)]
        out[d["id"]] = d
    return out


def set_cell(cell, text: str, *, bold=False):
    cell.text = ""
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    run = p.add_run(text)
    run.bold = bold
    run.font.name = BODY_FONT
    run.font.size = Pt(TABLE_PT)
    rpr = run._element.get_or_add_rPr()
    rf = rpr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rFonts")
    if rf is not None:
        rf.set("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", BODY_FONT)


def find_table(doc, *, first_cell: str, must_contain: str):
    for t in doc.tables:
        if t.rows[0].cells[0].text.strip() != first_cell:
            continue
        body = "\n".join(c.text for r in t.rows for c in r.cells)
        if must_contain in body:
            return t
    return None


def main() -> int:
    if not SRC.exists():
        raise SystemExit(f"v3 를 찾을 수 없습니다: {SRC}")
    shutil.copy2(SRC, DST)
    doc = docx.Document(str(DST))
    runs = load_runs()
    if len(runs) != 6:
        raise SystemExit(f"실행 기록이 6건이어야 합니다 (현재 {len(runs)}건)")

    # ── A. 실행 조건표 ────────────────────────────────────────────────────
    cond = find_table(doc, first_cell="구분", must_contain="마스터 212건")
    if cond is None:
        print("  실행 조건표를 찾지 못했습니다 (이미 교정됨?)")
    else:
        fixed = {
            "대상 데이터": (
                "수출 제조 중견기업 공급망 모사 — 마스터·트랜잭션 합계 7,396행. "
                "전량 원본 업무 시스템에 두고 지식그래프에 복제하지 않음 (그래프 인스턴스 0건)"),
            "연계 계층": (
                "이기종 4개 시스템 — ERP·관세(PostgreSQL) / WMS·CRM(MySQL). 시스템마다 키 표기가 "
                "다른 상태를 그대로 둠(품목: item_id / sku_code / ref_item_code, 통관 시스템은 "
                "외래키 부재). Data Fabric 이 각각 메타데이터 자동 수집 → 카탈로그 그래프 적재 "
                "(테이블 11 / 컬럼 109 자동 인식)"),
            "지식 계층": (
                "「기업 공급망 관리 업무 개념 체계」 문서를 먼저 작성하고 그 문서로 온톨로지를 구축 — "
                "클래스 20종 = 기록 개념 11종(데이터소스 바인딩) + 판단 개념 9종(어느 시스템에도 "
                "데이터가 없는 개념: 납기리스크·페널티발동요건·통관보류사유·품목분류적합성·"
                "재고커버일수·안전재고이탈·대체소싱후보·계약갱신우선순위·공급중단영향), 관계 35종. "
                "업무 규칙(R1~R9)을 클래스 설명에 수록"),
        }
        for row in cond.rows:
            key = row.cells[0].text.strip()
            if key in fixed:
                set_cell(row.cells[1], fixed[key])
                print(f"  실행 조건표 · {key} 교정")

    # ── B. 결과표 ─────────────────────────────────────────────────────────
    res = find_table(doc, first_cell="#", must_contain="도구 호출")
    if res is None:
        print("  결과표를 찾지 못했습니다")
    else:
        # 조회 시스템 열을 하나 덧붙인다 (판정 앞).
        header = [c.text.strip() for c in res.rows[0].cells]
        add_column = "조회 시스템" not in header
        if add_column:
            # 열은 끝에 붙지만 의미상 '판정' 앞이다. 헤더도 그 순서로 다시 쓴다 —
            # 안 그러면 머리글은 '판정 | 조회 시스템', 값은 'ERP, WMS | 충족' 로 어긋난다.
            res.add_column(Pt(90))
            set_cell(res.rows[0].cells[-2], "조회 시스템", bold=True)
            set_cell(res.rows[0].cells[-1], "판정", bold=True)
        for i, key in enumerate(ORDER, start=1):
            r = runs[key]
            row = res.rows[i]
            set_cell(row.cells[3], f"{r['tool_calls']}회")
            set_cell(row.cells[4], f"{r['tool_errors']}건")
            set_cell(row.cells[5], f"{r['elapsed_s']:.0f}초")
            if add_column:
                set_cell(row.cells[6], ", ".join(r["systems"]))
                set_cell(row.cells[7], "충족" if r["passed"] else "미충족")
            else:
                set_cell(row.cells[6], ", ".join(r["systems"]))
        total = res.rows[-1]
        set_cell(total.cells[3], f"{sum(r['tool_calls'] for r in runs.values())}회", bold=True)
        set_cell(total.cells[4], f"{sum(r['tool_errors'] for r in runs.values())}건", bold=True)
        set_cell(total.cells[5], f"{sum(r['elapsed_s'] for r in runs.values()):.0f}초", bold=True)
        if add_column:
            set_cell(total.cells[6], "4개 시스템", bold=True)
            set_cell(total.cells[7], f"{sum(1 for r in runs.values() if r['passed'])}/6 충족", bold=True)
        else:
            set_cell(total.cells[6], "4개 시스템", bold=True)
        print(f"  결과표 교정 (합계 {sum(r['tool_calls'] for r in runs.values())}회)")

    # ── C. 주석 ──────────────────────────────────────────────────────────
    for i, p in enumerate(doc.paragraphs):
        if p.text.strip().startswith("※ 판정 기준"):
            note = doc.add_paragraph()
            p._p.addnext(note._p)
            pf = note.paragraph_format
            pf.space_before = Pt(2)
            pf.space_after = Pt(8)
            run = note.add_run(
                "※ 본 실행 조건은 최초 구성을 한 차례 되돌린 뒤의 것이다. 첫 구성은 단일 "
                "PostgreSQL 스키마의 테이블 구조에서 클래스를 만들고 마스터 212건을 지식그래프에 "
                "적재했으나, ① 지식지도가 데이터의 사본이 되고 ② 연계 계층이 할 일이 없으며 "
                "③ 판단 개념이 만들어지지 않는 문제가 있어 개념 문서에서 출발하는 순서로 "
                "재구성하였다. 위 수치는 전부 재구성 이후 실측이다.")
            run.font.name = BODY_FONT
            run.font.size = Pt(9)
            rpr = run._element.get_or_add_rPr()
            rf = rpr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rFonts")
            if rf is not None:
                rf.set("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", BODY_FONT)
            print("  재구성 주석 삽입")
            break

    # ── D. 다른 절에 남은 옛 합계(44회) ────────────────────────────────
    total_calls = sum(r["tool_calls"] for r in runs.values())
    replaced = 0
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                if "44회" not in cell.text:
                    continue
                fixed_text = cell.text.replace("44회", f"{total_calls}회")
                set_cell(cell, fixed_text)
                replaced += 1
    for para in doc.paragraphs:
        # 재구성 경위를 적은 주석은 건드리지 않는다 — 거기 212건은 '옛 구성'을 가리킨다.
        if "44회" in para.text and "되돌린 뒤의 것이다" not in para.text:
            for run in para.runs:
                if "44회" in run.text:
                    run.text = run.text.replace("44회", f"{total_calls}회")
                    replaced += 1
    if replaced:
        print(f"  다른 절의 옛 합계 {replaced}곳을 {total_calls}회로 교정")

    doc.save(str(DST))
    print(f"\n저장: {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
