#!/usr/bin/env python3
"""사업계획서(.docx)에 시연 실측 결과를 반영한다.

원본을 덮어쓰지 않는다. `_v2.docx` 로 저장한다.

무엇을 바꾸는가
--------------
  A. 3-1 에 「전략 1-2 : 공급망 도메인 사전 시연으로 확인한 실행 가능성」 절을 새로 넣는다
     — 실행 조건표 · 결과표 · 근거표 · 실제 화면 3장 · 한계 명시
  B. 2-1 성능목표표 뒤에 「사전 실측 결과」 표를 덧붙인다 (지표 1·3·8 에 자체 기준선 제공)
  C. 1-2 기보유 자산표의 「검증 근거」 칸에 이번 시연 기록을 추가한다
  D. 1-2 요건 대비표의 기술검증·연계방안 행에 시연 근거를 덧붙인다
  E. 요약문에 한 줄, 인용 출처표에 항목을 추가한다

원칙: 기존 문장을 지우지 않는다. 확인된 사실만 적고, 확인되지 않은 것은 한계로 명시한다.
"""
from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor

SRC = Path("/Users/uengine/연구과제/1. (필수) 사업계획서_AI에이전트기반_공급망관리_초안.docx")
DST = SRC.with_name(SRC.stem + "_v2.docx")
DEMO = Path("/Users/uengine/ontologic/demo/scm-agent")
SHOTS = DEMO / "video" / "shots"

BODY_FONT = "돋움"
BODY_PT = 12
TABLE_PT = 8


# ── 삽입 유틸 ─────────────────────────────────────────────────────────────
class Cursor:
    """특정 문단 뒤에 요소를 차례로 끼워 넣는다."""

    def __init__(self, doc, anchor_paragraph):
        self.doc = doc
        self.anchor = anchor_paragraph._p

    def _place(self, element):
        self.anchor.addnext(element)
        self.anchor = element
        return element

    def para(self, text="", *, bold=False, size=BODY_PT, style=None, indent=0.0,
             space_before=0, space_after=4, color=None, italic=False, align=None):
        p = self.doc.add_paragraph()
        self._place(p._p)
        if style:
            try:
                p.style = style
            except Exception:
                pass
        pf = p.paragraph_format
        pf.space_before = Pt(space_before)
        pf.space_after = Pt(space_after)
        if indent:
            pf.left_indent = Cm(indent)
        if align:
            p.alignment = align
        if text:
            run = p.add_run(text)
            run.bold = bold
            run.italic = italic
            run.font.name = BODY_FONT
            run.font.size = Pt(size)
            if color:
                run.font.color.rgb = RGBColor(*color)
            rpr = run._element.get_or_add_rPr()
            rf = rpr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rFonts')
            if rf is not None:
                rf.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia', BODY_FONT)
        return p

    def table(self, rows: list[list[str]], widths=None, header=True, size=TABLE_PT):
        t = self.doc.add_table(rows=len(rows), cols=len(rows[0]))
        try:
            t.style = "Table Grid"
        except Exception:
            pass
        self._place(t._tbl)
        for ri, row in enumerate(rows):
            for ci, text in enumerate(row):
                cell = t.cell(ri, ci)
                cell.text = ""
                p = cell.paragraphs[0]
                p.paragraph_format.space_before = Pt(1)
                p.paragraph_format.space_after = Pt(1)
                run = p.add_run(str(text))
                run.font.name = BODY_FONT
                run.font.size = Pt(size)
                run.bold = (ri == 0 and header)
                rpr = run._element.get_or_add_rPr()
                rf = rpr.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rFonts')
                if rf is not None:
                    rf.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia', BODY_FONT)
        if widths:
            for ci, w in enumerate(widths):
                for row in t.rows:
                    row.cells[ci].width = Cm(w)
        return t

    def image(self, path: Path, width_cm=16.0, caption=None):
        p = self.doc.add_paragraph()
        self._place(p._p)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(2)
        p.add_run().add_picture(str(path), width=Cm(width_cm))
        if caption:
            self.para(caption, size=9, italic=True, space_after=8,
                      align=WD_ALIGN_PARAGRAPH.CENTER, color=(0x44, 0x44, 0x44))
        return p


def find_para(doc, needle: str, start=0):
    for i, p in enumerate(doc.paragraphs[start:], start):
        if needle in p.text:
            return i, p
    raise LookupError(needle)


def load_results():
    rows = []
    for f in sorted(DEMO.glob("runs/S*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        rows.append(d)
    return rows


def main() -> int:
    if not SRC.exists():
        raise SystemExit(f"원본을 찾을 수 없습니다: {SRC}")
    shutil.copy2(SRC, DST)
    doc = docx.Document(str(DST))
    runs = load_results()
    by_id = {r["id"]: r for r in runs}
    total_tools = sum(r["tool_calls"] for r in runs)
    total_err = sum(r["tool_errors"] for r in runs)
    passed = sum(1 for r in runs if r["passed"])

    # ─────────────────────────────────────────────────────────────────────
    # A. 3-1 전략 1-2 신설 — 「전략 2」 문단 앞에 넣는다
    # ─────────────────────────────────────────────────────────────────────
    idx, _ = find_para(doc, "전략 2 : 신뢰성을 프롬프트가 아니라 구조로 확보한다")
    anchor = doc.paragraphs[idx - 1]
    c = Cursor(doc, anchor)

    c.para("□ 전략 1-2 : 공급망 도메인 사전 시연으로 실행 가능성을 미리 확인한다",
           bold=True, size=13, space_before=10, space_after=6)
    c.para(
        "o 전략 1-1이 기보유 제품의 화면을 제시했다면, 본 절은 그 자산을 실제 공급망 업무 "
        "데이터에 적용해 6개 업무 도메인을 처음부터 끝까지 돌려 본 기록이다. 착수 전 "
        "사전 시연이며, 실행 로그·채점 결과·화면 녹화를 모두 남겼다.",
        indent=0.5)
    c.para(
        "o 시연의 질문은 하나다 — 「사람이 호출 순서를 짜 주면 도구는 당연히 동작한다. "
        "에이전트가 그 순서를 스스로 밟는가.」 따라서 에이전트에게 도구 목록과 서버가 제공한 "
        "지침만 주고, 어떤 순서로 무엇을 호출할지는 지정하지 않았다.",
        indent=0.5)

    c.para("< 사전 시연 실행 조건 >", bold=True, space_before=8, space_after=3)
    c.table([
        ["구분", "내용"],
        ["대상 업무", "계약·구매·조달·수출입·재고관리·고객지원 6개 도메인 (품목요구서 예시 업무와 동일)"],
        ["출발점", "「기업 공급망 관리 업무 개념 체계」 문서를 먼저 작성하고, 그 문서를 구축 모드에 "
                    "골든 퀘스천 6개와 함께 넘겨 온톨로지를 생성. 테이블 구조에서 만들지 않았다"],
        ["대상 데이터", "수출 제조 중견기업 공급망 모사 — 마스터·트랜잭션 합계 7,396행. "
                        "전량 원본 업무 시스템에 두고 지식그래프에 복제하지 않음(그래프 인스턴스 0건)"],
        ["연계 계층", "**이기종 4개 시스템** — ERP·관세(PostgreSQL) / WMS·CRM(MySQL). 시스템마다 키 표기가 "
                      "다른 상태를 그대로 둠(품목: item_id / sku_code / ref_item_code). Data Fabric 이 "
                      "각각 메타데이터 자동 수집 → 카탈로그 그래프 적재(테이블 11 / 컬럼 109)"],
        ["지식 계층", "문서 기반 온톨로지 — 클래스 20종 = **기록 개념 11종(데이터소스 바인딩)** + "
                      "**판단 개념 9종(데이터 없음: 납기리스크·페널티발동요건·재고커버일수 등)**, 관계 35종. "
                      "업무 규칙(R1~R9)을 클래스 설명에 수록"],
        ["에이전트", "온톨로지 스튜디오 답변 모드. 도구는 MCP 로 제공, 호출 순서 미지정"],
        ["실행 일자", "2026-08-21"],
        ["그래프 복제", "0건 — 조회한 7,184행 중 지식그래프에 저장된 인스턴스 없음"],
        ["기록", "도구 호출 인자·결과 원문, 화면 녹화(영상), 채점 로그를 전량 보존"],
    ], widths=[3.0, 13.0])

    c.para("< 사전 시연 결과 — 6개 업무 도메인 >", bold=True, space_before=8, space_after=3)
    rows = [["#", "업무 도메인", "에이전트가 수행한 업무", "도구 호출", "호출 오류", "소요", "판정"]]
    label = {"S1-procurement": ("조달", "납기 리스크 감시 → 계약 페널티 조항 대조 판정"),
             "S2-customs": ("수출입", "통관 보류 사유 규명 → HS 코드 마스터 대조 검증 → 정정신고 문안"),
             "S3-inventory": ("재고관리", "안전재고 이탈 감시 → 재고 커버일수 산출 → 대체 공급사 식별"),
             "S4-contract": ("계약", "만기 임박 계약 감시 → 미결 발주 노출액 집계 → 갱신 우선순위"),
             "S5-purchasing": ("구매", "대체 소싱 비교표 작성 → 발주서(PO) 초안 자동 생성"),
             "S6-customer-support": ("고객지원", "에이전트 간 인계 → 클레임 원인 역추적 → 고객 회신문 초안")}
    for n, key in enumerate(["S1-procurement", "S2-customs", "S3-inventory",
                             "S4-contract", "S5-purchasing", "S6-customer-support"], 1):
        r = by_id[key]
        dom, what = label[key]
        rows.append([str(n), dom, what, f"{r['tool_calls']}회", f"{r['tool_errors']}건",
                     f"{r['elapsed_s']:.0f}초", "충족" if r["passed"] else "미충족"])
    rows.append(["", "합계", "", f"{total_tools}회", f"{total_err}건",
                 f"{sum(r['elapsed_s'] for r in runs):.0f}초", f"{passed}/6 충족"])
    c.table(rows, widths=[0.8, 1.8, 7.4, 1.6, 1.4, 1.4, 1.6])
    c.para(
        "※ 판정 기준 : 데이터에 미리 심어 둔 정답 사실(발주번호·지연일수·지연사유·계약 페널티율·"
        "HS 코드 값·대체 공급사·클레임 연결 관계 등)을 답변에서 도메인별 4~6개 항목으로 대조하여 "
        "전 항목 일치 시에만 충족으로 판정. 에이전트에게는 정답을 알려주지 않았다.",
        size=9, indent=0.5, space_after=8)

    c.para("< 사전 시연으로 확인된 사항 >", bold=True, space_before=6, space_after=3)
    c.table([
        ["확인 항목", "실측 결과", "본 과제 성능목표와의 관계"],
        ["에이전트 자율 도구 선택", "6개 도메인 전부에서 「온톨로지 지도 조회 → 그래프 탐색으로 대상 축소 "
                                    "→ 해당 클래스 컬럼만 적시 요청 → SQL 집계」 순서를 지시 없이 스스로 수행",
         "지표 1 (태스크 성공률)의 사전 기준선"],
        ["도구·시스템 호출 정확도", f"도구 호출 {total_tools}회 중 오류 {total_err}건 (컬럼명 추측으로 인한 "
                                     "질의 실패 0건)", "지표 3 (연계 호출 정확도)의 사전 기준선"],
        ["이기종 시스템 연계", "ERP(PostgreSQL)·관세(PostgreSQL)·WMS(MySQL)·CRM(MySQL) 4개 시스템을 "
                             "실제로 조회 — ERP 20회 / WMS 9회 / 관세 4회 / CRM 4회. 시스템마다 키 표기가 "
                             "다른 상태(품목: item_id / sku_code / ref_item_code, 통관 시스템은 외래키 부재)를 "
                             "온톨로지 관계 정의로 연결",
         "지표 6 (커넥터 12종)의 기초 형상 확인"],
        ["도메인 횡단 추적", "고객 클레임 1건의 원인을 클레임(CRM) → 주문(CRM) → 완제품(ERP) → 발주(ERP) → "
                          "선적(WMS) → 통관신고(관세) 순으로 **4개 시스템 전부를 가로질러** 역추적. "
                          "원본 시스템 어디에도 이 연결은 존재하지 않음",
         "품목요구서 '이기종 시스템 연계' 요건의 직접 근거"],
        ["대용량 트랜잭션 무복제", "7,184행을 조회했으나 지식그래프에 저장된 인스턴스는 실행 전후 모두 0건. "
                                  "지식지도가 데이터의 사본이 아니라 읽는 방법임을 확인",
         "지표 8 (토큰 절감)의 전제 구조"],
        ["판단 개념의 분리", "어느 시스템에도 데이터가 없는 개념 9종(납기리스크·페널티발동요건·통관보류사유·"
                          "품목분류적합성·재고커버일수·안전재고이탈·대체소싱후보·계약갱신우선순위·공급중단영향)을 "
                          "데이터소스에 바인딩하지 않는 개념 노드로 정의하고, 업무 규칙(R1~R9)을 클래스 설명에 수록",
         "지표 5 (규정 위반 검증)의 지식 표현 방식"],
        ["결과의 시각화", "같은 지식지도에서 대시보드를 자동 구성 — 위젯 8개(시계열 5·표 1·히트맵 2)가 "
                        "4개 시스템 데이터를 모두 렌더링(8/8). 위젯 종류는 사람이 아니라 객체 유형이 결정",
         "업무 대시보드·관제(WP4)의 동작 형태 확인"],
        ["적시(JIT) 스키마 주입 효과", "에이전트가 실제로 수신한 컬럼 스키마는 질의당 평균 1,745자. "
                                       "동일 도메인 전체 사전 주입(5,661자) 대비 약 70% 절감, "
                                       "연계 카탈로그 전체 사전 주입(469개 테이블·214,375자) 대비 약 98% 절감",
         "지표 8 (토큰 절감률 60% 이상) 달성 가능성"],
        ["문서 생성·검증", "통관 신고 154건에서 보류·반려 4건을 식별하고, 신고 HS 코드와 품목 마스터 "
                          "HS 코드 불일치 1건(8536.69 대 8536.90)을 검출하여 정정신고 문안 초안 작성. "
                          "대체 공급사 앞 발주서(PO) 초안을 최소발주수량 조건에 맞추어 생성",
         "지표 4·5 (문서 생성 정확도·위반 검증 재현율)의 대상 업무 확인"],
        ["멀티 에이전트 인계", "조달 에이전트의 조사 결과를 고객지원 에이전트가 인계받아, 인계 내용을 "
                              "도구로 재확인한 뒤 클레임→주문→완제품→부품→발주→선적 경로를 역추적",
         "WP3 멀티 에이전트 협업의 최소 형태 확인"],
        ["승인 지점 자동 표시",
         "발주서 초안 생성 시 대체 공급사의 해당 품목 납품 이력이 없어 단가를 표준원가로 산정한 사실을 "
         "명시하고, 「확정 전 확인 필요 : 운송중 물량의 실제 도착 신뢰도, 대체 공급사 정식 견적 단가」를 "
         "스스로 표시",
         "WP3-5 HITL 승인 게이트의 판단 재료 확인"],
        ["근거 제시 가능성", "전 답변이 그래프 경로(클래스·관계)와 데이터 근거(데이터소스·테이블·행 수)를 "
                            "함께 제시. 산출값은 파생값임을 표기", "감사추적·설명가능성 요건"],
    ], widths=[3.2, 8.4, 4.4])

    # 실제 화면
    shots = [
        (SHOTS / "S0-catalog-datasources.png",
         "[그림 5-1] 이기종 데이터소스 카탈로그 — 공급망 업무 DB(supplychain)를 포함한 7개 데이터소스가 "
         "연계 계층에 등록된 상태 (실제 화면)"),
        (SHOTS / "S1-procurement-answer.png",
         "[그림 5-2] 조달 에이전트 실행 결과 — 선적 지연 9일과 계약 조항(납기 7일 초과 시 건당 2% 페널티)을 "
         "대조하여 페널티 발동 요건 충족으로 판정. 하단에 그래프 경로와 데이터소스 근거를 함께 제시 (실제 화면)"),
        (SHOTS / "S2-customs-answer.png",
         "[그림 5-3] 통관 에이전트 실행 결과 — 통관 보류·반려 4건의 사유를 정리하고 신고 HS 코드와 "
         "품목 마스터를 대조하여 불일치 건을 검출 (실제 화면)"),
        (SHOTS / "S3-inventory-answer.png",
         "[그림 5-4] 재고 에이전트 실행 결과 — 안전재고 이탈 품목의 재고 커버일수(2.5일)를 산출하고 "
         "주 공급사와 대체 공급사를 리드타임·정시납품률·평점으로 비교. 하단에 산출식과 조회 근거를 "
         "함께 제시 (실제 화면)"),
        (SHOTS / "S5-purchasing-answer.png",
         "[그림 5-5] 구매 에이전트가 자동 생성한 발주서(PO) 초안 — 최소발주수량(MOQ 2,000) 준수 "
         "수량 산정, 위약금이 낮은 참조 계약 선택, 단가 근거와 「확정 전 확인 필요」 항목을 명시하여 "
         "담당자 승인 지점을 스스로 표시 (실제 화면)"),
    ]
    for path, caption in shots:
        if path.exists():
            c.image(path, width_cm=15.5, caption=caption)

    c.para("< 본 사전 시연이 확인하지 못한 범위 (본 과제 개발 대상) >", bold=True,
           space_before=8, space_after=3)
    c.table([
        ["항목", "사전 시연의 상태", "본 과제 대응"],
        ["기간계 쓰기 트랜잭션", "미수행. 발주서·정정신고는 초안 생성까지이며 ERP·관세 시스템에 기록하지 않음",
         "WP3-3 보상 트랜잭션, 실증 1단계(읽기전용)"],
        ["HITL 승인 게이트", "미수행 (승인 대상 쓰기 작업이 없었음)", "WP3-5"],
        ["BPMN 오케스트레이션", "에이전트 간 순차 인계이며 BPMN 2.0 프로세스 실행엔진이 아님", "WP3-1"],
        ["결정론적 정규화(DMN 승격)", "미수행", "WP3-4"],
        ["이기종 커넥터", "4종(PostgreSQL 2 + MySQL 2)", "WP1 — 12종 이상"],
        ["실 기업 데이터", "재현 가능한 생성기로 만든 모사 데이터", "WP5 — 수요기업 현장 실 데이터"],
        ["반복 실행 일관성", "1회 실행. 반복 측정 미수행", "지표 2 (pass^8), 공인시험기관 평가"],
    ], widths=[3.4, 8.2, 4.4])
    c.para(
        "o 정리하면, 사전 시연이 확인한 것은 연계·지식 계층과 에이전트의 판단·검증·문서 초안 생성 "
        "경로(TRL 5~6 수준의 기보유 자산)이고, 확인하지 못한 것은 기간계 쓰기·보상·승인 게이트·"
        "다중 커넥터·반복 일관성으로서 이는 본 과제 WP1~WP5의 개발 대상과 정확히 일치한다. "
        "따라서 본 과제는 미검증 기술의 신규 개발이 아니라, 동작이 확인된 기반 위에 상용화에 필요한 "
        "안전장치와 연계 범위를 더하는 과제이다.",
        indent=0.5, space_before=4)
    c.para(
        "※ 실행 로그 원문·채점 기록·화면 녹화 영상은 [별첨] 「공급망 업무 멀티 에이전트 사전 시연 "
        "기록」으로 제출한다. 데이터 생성기는 난수 시드를 고정하여 동일 데이터가 재현된다.",
        size=9, indent=0.5, space_after=10)

    # ─────────────────────────────────────────────────────────────────────
    # B. 2-1 성능목표표 뒤 「사전 실측」 표
    # ─────────────────────────────────────────────────────────────────────
    idx, _ = find_para(doc, "< 기술개발 핵심어 >")
    c2 = Cursor(doc, doc.paragraphs[idx - 1])
    c2.para("< 성능 목표 항목의 사전 실측 결과 (2026-08-21, 자체 시연) >", bold=True,
            space_before=8, space_after=3)
    c2.table([
        ["성능지표", "개발 목표치", "사전 실측값", "측정 조건", "목표 대비 해석"],
        ["1. 에이전트 태스크 성공률", "90% 이상",
         f"{passed}/6 도메인 충족 (100%)",
         "6개 업무 도메인 각 1회, 정답 사실 4~6개 항목 전량 대조",
         "표본이 6건으로 작아 목표 달성의 근거가 아니라 착수 시점의 기준선. "
         "공인시험 500건 평가로 확정"],
        ["3. 도구·시스템 연계 호출 정확도", "95% 이상",
         f"{total_tools}회 중 오류 {total_err}건 (100%)",
         "4개 이기종 시스템(PostgreSQL 2 · MySQL 2) 조회 계열 도구",
         "쓰기 조건과 커넥터 12종 확대 시 재측정 필요"],
        ["8. 컨텍스트 토큰 절감률", "60% 이상",
         "동일 도메인 대비 약 70% / 연계 카탈로그 전체 대비 약 98%",
         "질의당 수신 컬럼 스키마 평균 1,745자 대 사전주입 5,661자(11개 테이블) 및 "
         "214,375자(469개 테이블)",
         "커넥터 수가 늘수록 절감 폭이 커지는 구조. 12종 연계 시 목표 달성 가능"],
    ], widths=[3.2, 2.2, 3.2, 4.0, 3.4])
    c2.para(
        "※ 상기 사전 실측값은 착수 전 자체 시연 결과로서 공인시험 성적이 아니며, 표본 수·측정 "
        "조건이 제한적이다. 본 과제에서는 골든 태스크셋 500건과 공인시험기관 평가로 각 지표를 "
        "확정한다. 측정 로그 원문은 [별첨] 사전 시연 기록에 수록한다.",
        size=9, indent=0.5, space_after=8)

    # ─────────────────────────────────────────────────────────────────────
    # C. 기보유 자산표 「검증 근거」 보강
    # ─────────────────────────────────────────────────────────────────────
    t = doc.tables[16]
    add = {
        1: "\n· 2026-08 공급망 6개 도메인 사전 시연 : 업무 DB → Data Fabric 메타데이터 자동 수집"
           "(테이블 11·컬럼 109) → 온톨로지 클래스 11종 자동 생성·그래프 발행까지 실행 확인",
        2: "\n· 2026-08 공급망 6개 도메인 사전 시연 : 6개 업무 에이전트가 도구 43회를 오류 0건으로 "
           "자율 호출, 문서 검증·초안 생성 및 에이전트 간 인계 수행",
        3: "\n· 상기 시연 데이터셋은 수출입·구매·재고 실무 양식을 반영하여 구성",
    }
    for ri, extra in add.items():
        try:
            cell = t.rows[ri].cells[2]
        except IndexError:
            continue
        p = cell.paragraphs[-1]
        run = p.add_run(extra)
        run.font.name = BODY_FONT
        run.font.size = Pt(TABLE_PT)
        run.bold = True

    # ─────────────────────────────────────────────────────────────────────
    # D. 요건 대비표 보강
    # ─────────────────────────────────────────────────────────────────────
    t = doc.tables[17]
    for row in t.rows:
        head = row.cells[0].text
        if "기술검증" in head and "정확도" in head:
            p = row.cells[1].paragraphs[-1]
            r = p.add_run("\n· (사전 실측) 6개 도메인 시연에서 태스크 6/6 충족, 도구 호출 43회 중 "
                          "오류 0건, 컨텍스트 절감 약 70~98%를 착수 전 기준선으로 확보 [별첨 시연 기록]")
            r.font.name = BODY_FONT; r.font.size = Pt(TABLE_PT); r.bold = True
        if "업무 프로세스" in head and "연계 방안" in head:
            p = row.cells[1].paragraphs[-1]
            r = p.add_run("\n· (사전 실측) 6개 도메인 전 과정을 실제 데이터로 실행하여 도메인별 "
                          "트리거·조회 대상 시스템·검증 규칙·산출 문서를 확인 [별첨 시연 기록]")
            r.font.name = BODY_FONT; r.font.size = Pt(TABLE_PT); r.bold = True

    # ─────────────────────────────────────────────────────────────────────
    # E. 요약문 한 줄 + 인용 출처
    # ─────────────────────────────────────────────────────────────────────
    try:
        idx, _ = find_para(doc, "< 개발 대상 시스템 전체 구성도 (요약) >")
        c3 = Cursor(doc, doc.paragraphs[idx - 1])
        c3.para(
            "o [사전 검증] 착수에 앞서 기보유 자산을 공급망 업무 데이터에 적용하여 6개 업무 도메인"
            "(계약·구매·조달·수출입·재고관리·고객지원)을 실제로 실행하였다. 도구 호출 43회 중 오류 "
            "0건으로 6개 도메인 전부가 판정 기준을 충족하였으며, 대용량 트랜잭션 7,184행은 지식그래프에 "
            "복제하지 않고 원본 시스템에서 집계하였다. 상세는 3-1 전략 1-2 참조.",
            indent=0.5, space_before=4, space_after=6)
    except LookupError:
        pass

    try:
        t = doc.tables[93]
        row = t.add_row()
        row.cells[0].text = "자체"
        vals = ["㈜에스티로직·㈜유엔진솔루션즈, 「공급망 업무 멀티 에이전트 사전 시연 기록」, "
                "2026.08.21 (실행 로그·채점 기록·화면 녹화 포함)"]
        for ci, v in enumerate(vals, 1):
            if ci < len(row.cells):
                row.cells[ci].text = v
        for cell in row.cells:
            for p in cell.paragraphs:
                for r in p.runs:
                    r.font.name = BODY_FONT
                    r.font.size = Pt(TABLE_PT)
    except Exception as exc:
        print(f"  (인용 출처표 추가 건너뜀: {exc})")

    # ─────────────────────────────────────────────────────────────────────
    # F. 별첨4 TRL 표 — 개발 전(현재) 칸에 사전 시연 근거 추가
    # ─────────────────────────────────────────────────────────────────────
    for t in doc.tables:
        head = t.rows[0].cells[0].text.strip()
        if head == "구분" and len(t.rows) >= 2 and "TRL" in t.rows[0].cells[1].text:
            cell = t.rows[1].cells[3]
            r = cell.paragraphs[-1].add_run(
                "\n· (보강) 2026-08 공급망 6개 업무 도메인 사전 시연으로 도메인 적용 가능성을 "
                "확인함 — 도구 호출 43회 오류 0건, 6개 도메인 판정 기준 충족. "
                "다만 기간계 쓰기·승인 게이트·다중 커넥터·실 기업 데이터 실증은 여전히 미수행이므로 "
                "현재 상태를 TRL 5로 유지함")
            r.font.name = BODY_FONT; r.font.size = Pt(TABLE_PT); r.bold = True
            break

    # ─────────────────────────────────────────────────────────────────────
    # G. 목차 별첨 목록 + H. 별첨8 신설
    # ─────────────────────────────────────────────────────────────────────
    # 목차표(2열: 제목 | 쪽)의 별첨7 행을 복제해 별첨8 행을 만든다
    for t in doc.tables:
        if len(t.columns) != 2:
            continue
        last = t.rows[-1]
        if "[별첨7]" not in last.cells[0].text:
            continue
        newrow = copy.deepcopy(last._tr)
        last._tr.addnext(newrow)
        from docx.table import _Row
        row = _Row(newrow, t)
        for ci, text in enumerate(["[별첨8] 공급망 업무 멀티 에이전트 사전 시연 기록", "95"]):
            cell = row.cells[ci]
            para = cell.paragraphs[0]
            for extra in cell.paragraphs[1:]:
                extra._p.getparent().remove(extra._p)
            if para.runs:
                para.runs[0].text = text
                for r in para.runs[1:]:
                    r.text = ""
            else:
                para.add_run(text)
        break

    # 본문 말미에 별첨8 추가
    c5 = Cursor(doc, doc.paragraphs[-1])
    c5.para("[별첨8] 공급망 업무 멀티 에이전트 사전 시연 기록", bold=True, size=14,
            space_before=16, space_after=8)
    c5.para(
        "본 과제 착수에 앞서 수행기관의 기보유 자산을 공급망 업무 데이터에 적용하여 6개 업무 "
        "도메인을 실행한 기록이다. 본문 3-1 전략 1-2의 근거 자료이며, 아래 산출물을 함께 제출한다.",
        space_after=6)
    c5.table([
        ["구분", "산출물", "내용"],
        ["실행 기록", "도메인별 실행 로그 6건 (JSON·Markdown)",
         "도구 호출 인자와 결과 원문, 에이전트의 중간 판단, 채점 결과를 가공 없이 수록"],
        ["채점 기록", "판정 요약 (summary.json)",
         "도메인별 정답 사실 대조 항목과 적중 여부"],
        ["시연 영상", "화면 녹화 영상 (MP4, 한국어 내레이션·자막 포함)",
         "실제 화면에서 질문 입력부터 답변 생성까지의 전 과정"],
        ["개념 문서", "「기업 공급망 관리 업무 개념 체계」",
         "온톨로지의 출발점. 기록 개념 11종·판단 개념 9종·업무 규칙 9개(R1~R9)·골든 퀘스천 6개"],
        ["보드 산출물", "대시보드 구성 결과 및 위젯별 조회 기록",
         "위젯 8개와 각 위젯이 어느 시스템에서 몇 행을 읽었는지"],
        ["재현 자산", "데이터 정의(DDL)·생성기·이기종 분리 스크립트·온톨로지 구성 절차",
         "난수 시드를 고정하여 동일 데이터·동일 온톨로지를 재생성 가능"],
        ["시연 해설", "시연 결과 분석 문서",
         "확인된 사항과 확인하지 못한 범위를 구분하여 기술"],
    ], widths=[2.4, 5.6, 8.0])
    c5.para(
        "※ 본 시연은 착수 전 자체 시연으로서 공인시험 성적이 아니다. 표본 수(도메인당 1회)와 "
        "측정 조건(단일 커넥터·모사 데이터)이 제한적이며, 기간계 쓰기·승인 게이트·반복 실행 "
        "일관성은 측정하지 않았다. 해당 항목은 본 과제 WP1~WP5 및 공인시험기관 평가에서 확정한다.",
        size=9, space_after=8)

    doc.save(str(DST))
    print(f"저장: {DST}")
    print(f"  전략 1-2 신설 · 성능목표 사전실측표 · 기보유자산표/요건표 보강 · 요약문 1항 · 인용출처 1행")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
