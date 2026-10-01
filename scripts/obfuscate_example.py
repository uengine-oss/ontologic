#!/usr/bin/env python3
"""예제 스키마를 **의미가 드러나지 않는 레거시**로 바꾼다 (spec 008 / T1).

지금 번들된 manufacturing 예제는 메타데이터가 이미 완성돼 있다 — 이름이 `mfg_product`,
`product_name` 이고 FK 12개가 선언돼 있으며 컬럼마다 한글 주석이 붙어 있다. 그래서
**증강이 무엇을 보태는지 보이지 않고**, 온톨로지 구축의 테이블 선택이 이름 문자열만으로
풀린다.

이 스크립트는 그 예제를 뒤집는다. 이름을 코드로 바꾸고 FK 와 주석을 지워, 의미의 원천을
**스토어드 프로시저 코드와 실제 데이터 값**만 남긴다.

## 왜 "생성"인가 (spec FR-006)

난독화본을 손으로 써서 커밋하면 원본과의 대응이 사라진다. 그러면 "증강이 의미를 복원했는가"를
사람 눈으로만 볼 수 있다. 매핑에서 생성하면 **매핑 파일이 곧 정답지**가 되어 자동 채점이 된다.

## 무엇을 바꾸고 무엇을 남기는가

| 대상 | 처리 | 근거 |
|---|---|---|
| 테이블·컬럼 이름 | 코드로 치환 (`TB01`, `C001`) | FR-001 |
| `FOREIGN KEY` 절 | 제거 | FR-002 |
| 주석 | 제거 | FR-003 |
| 데이터 값 | **그대로** | FR-004 — 증강의 근거다 |
| `PRIMARY KEY` | 유지 | 난독화 대상이 아니다. 없으면 적재가 깨진다 |
| 프로시저 이름·주석·지역변수 | **그대로** | FR-005 — 레거시에서 의미가 남아 있는 자리 |
| 프로시저의 테이블·컬럼 참조 | 코드로 치환 | 실행 가능해야 한다 |

## 재작성이 조심하는 두 가지 (research R1)

1. **문자열 리터럴 안의 이름.** 값에 `'product_id'` 같은 문자열이 있으면 순진한 치환이
   데이터를 바꾼다. FR-004 위반이다. → 렉서가 `'...'`(`''` 이스케이프 포함)와 주석을 건너뛴다.
2. **접두사 겹침.** `product_id` 를 먼저 치환하면 `mfg_product` 안의 `product` 가 이미 바뀐
   뒤라 매칭이 깨진다. → **길이 내림차순** 치환 + 단어 경계.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("pyyaml 이 필요합니다:  uv run --with pyyaml python scripts/obfuscate_example.py ...")


# ── SQL 렉서 ────────────────────────────────────────────────────────────────
#
# 완전한 SQL 파서가 아니다. 필요한 것은 "어디가 코드이고 어디가 문자열/주석인가" 하나뿐이라
# 그 경계만 정확히 잡는다. PostgreSQL DDL·DML 과 Oracle 방언 프로시저를 **같은 도구로**
# 다뤄야 하므로 방언 파서를 쓰지 않는다.

_CODE = "code"
_STR = "string"     # 문자열 리터럴 — **절대** 치환하지 않는다 (FR-004: 값은 원본 그대로)
_COMMENT = "comment"  # 주석 — 파일 종류에 따라 지우거나, 식별자만 치환한다


def _segments(sql: str) -> list[tuple[str, str]]:
    """SQL 을 (종류, 조각) 목록으로 자른다. 종류는 ``code`` / ``string`` / ``comment``.

    주석과 문자열을 **다른 종류로** 가르는 이유: 둘의 처리가 다르다. 문자열은 업무 데이터라
    무조건 보존해야 하지만(FR-004), 주석은 프로시저에서 **식별자만 치환**해야 한다 — 안 그러면
    주석의 「참조 테이블: manufacturing.mfg_product」가 정답을 그대로 알려준다.
    """
    out: list[tuple[str, str]] = []
    buf: list[str] = []
    i, n = 0, len(sql)

    def flush() -> None:
        if buf:
            out.append((_CODE, "".join(buf)))
            buf.clear()

    while i < n:
        ch = sql[i]

        # 홑따옴표 문자열 — '' 는 이스케이프된 따옴표이지 종료가 아니다.
        if ch == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            flush()
            out.append((_STR, sql[i:j]))
            i = j
            continue

        # 겹따옴표 식별자 — 안의 이름은 치환 대상이지만 이 예제에는 없다.
        # 있으면 코드로 두어 일반 치환이 처리하게 한다.

        # 줄 주석
        if sql.startswith("--", i):
            j = sql.find("\n", i)
            j = n if j == -1 else j
            flush()
            out.append((_COMMENT, sql[i:j]))
            i = j
            continue

        # 블록 주석
        if sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            j = n if j == -1 else j + 2
            flush()
            out.append((_COMMENT, sql[i:j]))
            i = j
            continue

        buf.append(ch)
        i += 1

    flush()
    return out


def _rename_code(code: str, table: re.Pattern, mapping: dict[str, str]) -> str:
    return table.sub(lambda m: mapping[m.group(0).lower()], code)


def rewrite(sql: str, mapping: dict[str, str], *, strip_comments: bool) -> str:
    """식별자를 치환한다. **문자열 리터럴은 절대 건드리지 않는다** (FR-004).

    주석 처리가 파일 종류에 따라 갈린다.

    - ``strip_comments=True`` (스키마 DDL·DML): 주석을 **지운다** (FR-003).
    - ``strip_comments=False`` (프로시저): 주석을 **남기되 식별자는 치환한다** (FR-005).

    프로시저 주석을 그대로 두면 안 되는 이유: 원본 주석의 머리말이
    ``-- 참조 테이블: manufacturing.mfg_daily_process_metrics`` 처럼 **원본 테이블명을 그대로
    적는다.** 그러면 증강이 코드를 분석할 필요 없이 주석에서 정답을 읽어 버려 시나리오가
    무너진다. 남겨야 하는 것은 *설명*("일별 공정 지표를 집계한다")이지 *식별자*가 아니다.
    """
    if not mapping:
        return sql
    # 길이 내림차순 — 접두사 겹침 방지 (research R1)
    names = sorted(mapping, key=len, reverse=True)
    pattern = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in names) + r")\b", re.IGNORECASE)

    parts: list[str] = []
    for kind, chunk in _segments(sql):
        if kind == _CODE:
            parts.append(_rename_code(chunk, pattern, mapping))
        elif kind == _COMMENT:
            if strip_comments:
                continue
            parts.append(_rename_code(chunk, pattern, mapping))
        else:  # _STR — 업무 데이터. 원본 그대로.
            parts.append(chunk)
    return "".join(parts)


# ── FK 제거 ─────────────────────────────────────────────────────────────────

def strip_foreign_keys(ddl: str) -> tuple[str, int]:
    """``FOREIGN KEY ... REFERENCES ...`` 절을 지운다 (FR-002).

    절만 지우면 앞 줄에 매달린 쉼표가 남아 문법 오류가 된다. 지운 뒤 `(...)` 목록의
    마지막 쉼표를 정리한다.
    """
    lines = ddl.split("\n")
    kept, removed = [], 0
    for line in lines:
        if re.match(r"\s*FOREIGN\s+KEY\s*\(", line, re.IGNORECASE):
            removed += 1
            continue
        kept.append(line)
    out = "\n".join(kept)
    # "마지막 항목, \n);"  →  "마지막 항목\n);"
    out = re.sub(r",(\s*\n\s*\);)", r"\1", out)
    return out, removed


# ── 매핑 ────────────────────────────────────────────────────────────────────

_CREATE_RE = re.compile(
    r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+(\w+)\.(\w+)\s*\((.*?)\n\);",
    re.IGNORECASE | re.DOTALL,
)
_COL_RE = re.compile(
    r"^\s*(\w+)\s+(?:VARCHAR|CHAR|INT|INTEGER|BIGINT|SMALLINT|DECIMAL|NUMERIC|DATE|"
    r"TIMESTAMP|TEXT|BOOLEAN|REAL|DOUBLE)",
    re.IGNORECASE,
)
_FK_RE = re.compile(
    r"FOREIGN\s+KEY\s*\((\w+)\)\s*REFERENCES\s+\w+\.(\w+)\s*\((\w+)\)",
    re.IGNORECASE,
)


def build_mapping(ddl: str, target_schema: str) -> dict:
    """원본 DDL 에서 매핑 뼈대를 만든다. ``label`` 은 사람이 채운다 (contracts/name-mapping.md).

    이름은 **결정적 규칙**으로 짓는다 — 테이블은 등장 순서 ``TB01``.., 컬럼은 **서로 다른 이름**
    기준 첫 등장 순서 ``C001``... 손으로 지으면 재현되지 않는다.

    ## 왜 컬럼 번호가 테이블별이 아니라 전역인가

    치환은 파일 전체를 훑는 한 벌의 사전으로 한다. 프로시저의 컬럼 참조는 `p.product_id` 처럼
    **별칭으로 한정**되어 있어, 어느 테이블의 컬럼인지 알려면 별칭을 해석해야 한다 — 그건 진짜
    SQL 파서의 일이고, 이 스크립트는 PostgreSQL DDL 과 Oracle 방언 프로시저를 **같은 도구로**
    다뤄야 해서 방언 파서를 쓰지 않는다 (research R1).

    그래서 사전이 전역이면 번호도 전역이어야 한다. 테이블별로 리셋해 놓고 전역 사전으로
    치환하면 **매핑(정답지)과 생성물이 어긋난다** — 채점기는 매핑을 정답으로 믿으므로 그
    어긋남은 조용히 틀린 채점이 된다. 실제로 초기 구현이 이 버그를 냈다: `created_date` 가
    TB01 에서 `C008` 을 받자 TB02 의 7번째 컬럼도 `C008` 이 되어 `C007` 이 비었다.

    같은 이름이 여러 테이블에서 같은 코드가 되는 것은 부작용이 아니라 **현실에 가깝다.**
    레거시 DB 도 같은 개념을 같은 컬럼명으로 쓴다. 조인 가능성이라는 구조 신호는 남지만,
    그것은 이름이 주는 **의미** 신호가 아니다 — 난독화의 목적은 유지된다.
    """
    tables, fks, source_schema = [], [], None
    col_code: dict[str, str] = {}  # 소스 컬럼명(소문자) → 코드. 전역 단일.
    for ti, m in enumerate(_CREATE_RE.finditer(ddl), start=1):
        schema, name, body = m.group(1), m.group(2), m.group(3)
        source_schema = source_schema or schema
        target = f"TB{ti:02d}"
        cols = []
        for line in body.split("\n"):
            cm = _COL_RE.match(line)
            if not cm:
                continue
            src = cm.group(1)
            code = col_code.setdefault(src.lower(), f"C{len(col_code) + 1:03d}")
            cols.append({"source": src, "target": code, "label": ""})
        tables.append({"source": name, "target": target, "label": "", "columns": cols})
        for fm in _FK_RE.finditer(body):
            fks.append(
                {
                    "source_from": {"table": name, "column": fm.group(1)},
                    "source_to": {"table": fm.group(2), "column": fm.group(3)},
                }
            )
    return {
        "version": 1,
        "schema": {"source": source_schema or "manufacturing", "target": target_schema},
        "tables": tables,
        "foreign_keys": fks,
    }


def resolve_fk_targets(doc: dict) -> None:
    """`foreign_keys[].from/to` 를 난독화 이름으로 채운다. 매핑이 완성된 뒤에 부른다."""
    tbl = {t["source"]: t for t in doc["tables"]}
    for fk in doc["foreign_keys"]:
        for side, key in (("source_from", "from"), ("source_to", "to")):
            src = fk[side]
            t = tbl.get(src["table"])
            if not t:
                continue
            col = next((c for c in t["columns"] if c["source"] == src["column"]), None)
            fk[key] = {"table": t["target"], "column": col["target"] if col else "?"}


def flatten(doc: dict) -> dict[str, str]:
    """치환 사전 — 소문자 키. 스키마·테이블·컬럼 이름을 한 벌로 모은다."""
    out = {doc["schema"]["source"].lower(): doc["schema"]["target"]}
    for t in doc["tables"]:
        out[t["source"].lower()] = t["target"]
        for c in t["columns"]:
            out.setdefault(c["source"].lower(), c["target"])
    return out


def check_mapping(doc: dict) -> list[str]:
    """계약 불변식 (contracts/name-mapping.md). 어기면 난독화에 구멍이 생긴다."""
    errs: list[str] = []
    seen: dict[str, str] = {}
    for t in doc["tables"]:
        if t["target"] in seen:
            errs.append(f"target 중복: {t['target']} ({t['source']} / {seen[t['target']]})")
        seen[t["target"]] = t["source"]
        cseen: dict[str, str] = {}
        for c in t["columns"]:
            key = f"{t['target']}.{c['target']}"
            if c["target"] in cseen:
                errs.append(f"target 중복: {key} ({c['source']} / {cseen[c['target']]})")
            cseen[c["target"]] = c["source"]
            if not re.fullmatch(r"C\d{3}", c["target"]):
                errs.append(f"컬럼 target 이 순번 코드가 아님: {key}={c['target']}")
        # 접두 한 글자(`TBS01`)까지 허용한다 — 같은 Neo4j 에 다른 난독화 예제(`TB01`…)가 이미
        # 있으면 이름만으로 테이블을 찾는 API 가 둘을 가르지 못한다(증권 0편에서 실측).
        if not re.fullmatch(r"TB[A-Z]?\d{2}", t["target"]):
            errs.append(f"테이블 target 이 순번 코드가 아님: {t['target']}")

    # ── 정답지와 치환 사전의 일치 ──
    #
    # 치환은 `flatten()` 이 만든 **이름 하나당 코드 하나**의 전역 사전으로 한다. 매핑이
    # 같은 이름에 테이블마다 다른 코드를 주면, 생성물은 사전을 따르고 매핑은 다른 말을 하게
    # 되어 **정답지가 거짓이 된다.** 채점기는 매핑을 정답으로 믿으므로 그 어긋남은 조용히
    # 틀린 채점으로 나타난다. 초기 구현이 실제로 이 버그를 냈다(build_mapping 주석).
    #
    # 여기서 잡지 않으면 증상은 한참 뒤 "증강했는데 점수가 안 오른다"로만 보인다.
    table = flatten(doc)
    for t in doc["tables"]:
        for c in t["columns"]:
            actual = table.get(c["source"].lower())
            if actual != c["target"]:
                errs.append(
                    f"정답지 불일치: {t['source']}.{c['source']} 는 매핑상 {c['target']} 인데 "
                    f"치환 사전은 {actual} 를 쓴다 — 같은 컬럼명은 전역 단일 코드여야 한다"
                )
    return errs


# ── 완전성 검사 ─────────────────────────────────────────────────────────────

def leaked_names(text: str, doc: dict) -> set[str]:
    """생성물에 **원본 이름이 남아 있는가.**

    남은 이름은 곧 의미가 새는 구멍이고, SC-001(증강 전 자동 바인딩 0건)이 0이 아닌 이유가
    된다.

    **코드와 주석을 모두 본다.** 처음에는 코드만 봤는데, 그러면 프로시저 주석의
    ``-- 참조 테이블: manufacturing.mfg_product`` 가 그대로 통과한다 — 실제로 놓쳤다.
    난독화를 무력화하는 가장 쉬운 길이 주석이므로 검사가 거기까지 닿아야 한다.

    문자열 리터럴만 제외한다. 값은 FR-004 로 원본 그대로 두는 것이 정상이고, 값 안에 우연히
    이름과 같은 문자열이 있어도 그것은 데이터이지 식별자가 아니다.
    """
    names = {t["source"].lower() for t in doc["tables"]}
    names |= {c["source"].lower() for t in doc["tables"] for c in t["columns"]}
    names.add(doc["schema"]["source"].lower())
    visible = "".join(
        chunk for kind, chunk in _segments(text) if kind in (_CODE, _COMMENT)
    ).lower()
    return {n for n in names if re.search(rf"\b{re.escape(n)}\b", visible)}


def header(mapping_path: Path, doc: dict) -> str:
    """생성물 머리말 — 매핑 해시를 남긴다.

    채점기는 매핑을 정답으로 믿으므로, 매핑과 생성물이 어긋나면 **조용히 틀린 답**이 나온다.
    해시로 그 어긋남을 잡는다 (contracts/name-mapping.md).
    """
    digest = hashlib.sha256(mapping_path.read_bytes()).hexdigest()
    # 원본 스키마·테이블 이름을 머리말에 적지 않는다. 생성물은 인제스천 입력이기도 해서,
    # 여기에 원본 이름을 적으면 **생성기가 정답을 파일에 흘리는 셈**이다. 처음엔 적었다가
    # 완전성 검사에 걸렸다. 해시만 남긴다 — 채점기가 매핑 일치를 확인하는 데 필요하다.
    return (
        "-- 이 파일은 scripts/obfuscate_example.py 가 생성했다. 직접 고치지 않는다.\n"
        f"-- mapping-sha256: {digest}\n\n"
    )


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="예제 스키마 난독화 (spec 008 T1)")
    ap.add_argument("--mapping", required=True, type=Path)
    ap.add_argument("--seed-dir", required=True, type=Path, help="seed/postgres 디렉터리")
    ap.add_argument("--tutorial-src", required=True, type=Path, help="원본 tutorial 디렉터리")
    ap.add_argument("--tutorial-out", required=True, type=Path, help="난독화 tutorial 출력")
    ap.add_argument("--target-schema", default="legacy")
    ap.add_argument("--init-mapping", action="store_true", help="매핑 뼈대만 만들고 끝낸다")
    args = ap.parse_args()

    ddl_path = args.seed_dir / "01_ddl_schema.sql"
    ddl = ddl_path.read_text(encoding="utf-8")

    if args.init_mapping:
        doc = build_mapping(ddl, args.target_schema)
        resolve_fk_targets(doc)
        args.mapping.parent.mkdir(parents=True, exist_ok=True)
        args.mapping.write_text(
            "# spec 008 난독화 매핑 (정답지). 계약: "
            "specs/008-legacy-metadata-to-ontology/contracts/name-mapping.md\n"
            "# target 은 생성기가 짓고, label 은 사람이 채운다.\n"
            + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        n_col = sum(len(t["columns"]) for t in doc["tables"])
        print(f"매핑 뼈대 생성: {args.mapping}")
        print(f"  테이블 {len(doc['tables'])} · 컬럼 {n_col} · FK {len(doc['foreign_keys'])}")
        print("  label 을 채운 뒤 --init-mapping 없이 다시 실행하세요.")
        return 0

    doc = yaml.safe_load(args.mapping.read_text(encoding="utf-8"))
    errs = check_mapping(doc)
    if errs:
        for e in errs:
            print(f"매핑 오류: {e}", file=sys.stderr)
        return 1

    mapping = flatten(doc)
    hdr = header(args.mapping, doc)
    problems: list[str] = []

    # 1) 스키마 DDL — FK 제거 + 주석 제거 + 이름 치환
    ddl_body, n_fk = strip_foreign_keys(ddl)
    legacy_ddl = rewrite(ddl_body, mapping, strip_comments=True)
    legacy_ddl = re.sub(r"\n{3,}", "\n\n", legacy_ddl)
    (args.seed_dir / "05_ddl_legacy.sql").write_text(hdr + legacy_ddl, encoding="utf-8")

    # 2) DML — 컬럼 목록만 치환. 값은 문자열 리터럴이라 렉서가 건너뛴다.
    dml_out: list[str] = [hdr]
    for name in ("02_dml_master_data.sql", "03_dml_timeseries_data.sql",
                 "04_dml_generated_timeseries.sql"):
        p = args.seed_dir / name
        if not p.exists():
            continue
        dml_out.append(rewrite(p.read_text(encoding="utf-8"), mapping, strip_comments=True))
    (args.seed_dir / "06_dml_legacy.sql").write_text("\n".join(dml_out), encoding="utf-8")

    # 3) 인제스천용 DDL
    #
    # 원본 파일 하나당 결과 파일 하나로 낸다. 예전에는 어느 입력을 읽든 결과를
    # `legacy_ddl.sql` **한 곳에 덮어썼다** — 입력이 하나뿐이라 우연히 맞았을 뿐이고,
    # 두 번째 DDL(예: crm)을 넣는 순간 먼저 것이 조용히 사라진다. 파일이 사라진 것이
    # 아니라 "난독화가 일부만 됐다" 로 보이므로 알아채기 어렵다.
    src_ddl = args.tutorial_src / "ddl"
    out_ddl = args.tutorial_out / "ddl"
    out_ddl.mkdir(parents=True, exist_ok=True)
    n_ddl = 0
    for p in sorted(src_ddl.glob("*.sql")):
        body, _ = strip_foreign_keys(p.read_text(encoding="utf-8"))
        text = re.sub(r"\n{3,}", "\n\n", rewrite(body, mapping, strip_comments=True))
        # `manufacturing_ddl.sql` → `legacy_ddl.sql`. 그 외에는 이름을 지킨다.
        out_name = "legacy_ddl.sql" if p.stem.endswith("_ddl") and "manufacturing" in p.stem \
            else p.name
        (out_ddl / out_name).write_text(hdr + text, encoding="utf-8")
        n_ddl += 1

    # 4) 프로시저 — 주석·지역변수는 그대로. 테이블/컬럼 참조만 치환 (FR-005)
    src_proc = args.tutorial_src / "procedures"
    out_proc = args.tutorial_out / "procedures"
    out_proc.mkdir(parents=True, exist_ok=True)
    n_proc = 0
    for p in sorted(src_proc.glob("*.sql")):
        (out_proc / p.name).write_text(
            rewrite(p.read_text(encoding="utf-8"), mapping, strip_comments=False),
            encoding="utf-8",
        )
        n_proc += 1

    # ── 완전성 검사 — 원본 이름이 코드에 남아 있으면 난독화에 구멍이 있다 ──
    for path in (args.seed_dir / "05_ddl_legacy.sql", args.seed_dir / "06_dml_legacy.sql",
                 out_ddl / "legacy_ddl.sql", *sorted(out_proc.glob("*.sql"))):
        leaked = leaked_names(path.read_text(encoding="utf-8"), doc)
        if leaked:
            problems.append(f"{path.name}: 원본 이름이 남음 — {sorted(leaked)[:8]}")

    n_col = sum(len(t["columns"]) for t in doc["tables"])
    print(f"생성 완료 — 테이블 {len(doc['tables'])} · 컬럼 {n_col} · FK 제거 {n_fk} · 프로시저 {n_proc}")
    print(f"  {args.seed_dir/'05_ddl_legacy.sql'}")
    print(f"  {args.seed_dir/'06_dml_legacy.sql'}")
    print(f"  {out_ddl/'legacy_ddl.sql'}")
    print(f"  {out_proc}/*.sql")

    if problems:
        print("\n난독화 불완전:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    print("완전성 검사 통과 — 코드 영역에 원본 이름 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
