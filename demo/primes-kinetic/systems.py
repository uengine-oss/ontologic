"""PriMES 마이크로서비스를 키네틱 레지스트리에 등록한다 (리허설용 — 영상에서는 시스템 등록 마법사로 한다).

스펙은 서비스 포트의 /v3/api-docs (springdoc), 호출은 PriMES 게이트웨이 :8080, 인증은 JSON 로그인 토큰.
비밀 값은 등록하지 않는다 — 게이트웨이 프로세스 env 의 PRIMES_LOGIN_ID / PRIMES_PASSWORD.
"""
import os
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "kinetic-mes"))
import seed  # noqa: E402  (dev-idp 토큰·kinetic 주소)

GATEWAY = os.environ.get("PRIMES_GATEWAY", "http://localhost:8080")
AUTH = {"kind": "login_token", "token_url": f"{GATEWAY}/api/auth/login", "login_body": {"tenant": "standard"},
        "username_env": "PRIMES_LOGIN_ID", "password_env": "PRIMES_PASSWORD", "token_path": "token"}
SYSTEMS = [  # name, port, 표시 이름, 설명, 아이콘, 담당
    ("primes-sales", 8083, "PriMES 영업", "수주 등록·변경·취소·출하", "erp", "영업팀"),
    ("primes-purchase", 8084, "PriMES 구매", "자재 소요(MRP)·구매 발주", "scm", "구매팀"),
    ("primes-production", 8085, "PriMES 생산", "작업지시 발행·변경·취소", "mes", "생산관리팀"),
    ("primes-mold", 8088, "PriMES 금형", "금형 수명·장착·탈착", "cmms", "금형팀"),
    ("primes-masterdata", 8082, "PriMES 기준정보", "고객·품목·BOM·단가", "generic", "기준정보팀"),
    ("primes-equipment", 8087, "PriMES 설비", "설비·라우팅 설비 상태", "mes", "설비팀"),
]


def body(name, port, display, desc, icon, team):
    return {"name": name, "display_name": display, "description": desc, "owner_team": team, "icon": icon,
            "tags": ["primes"], "protocol": "rest", "base_url": GATEWAY,
            "openapi_url": f"http://localhost:{port}/v3/api-docs", "health_path": "/actuator/health",
            "environments": [{"name": "dev", "base_url": GATEWAY}], "active_environment": "dev",
            "timeout_ms": 10000, "retries": 1, "auth": AUTH}


def admin_headers():
    return {"Authorization": f"Bearer {seed.token('admin', ['kinetic_admin'])}"}


def register(only: list[str] | None = None) -> list[str]:
    out = []
    for s in SYSTEMS:
        if only and s[0] not in only:
            continue
        r = httpx.post(f"{seed.KINETIC_API}/api/kinetic/systems", headers=admin_headers(), json=body(*s), timeout=30)
        r.raise_for_status()
        out.append(f"{s[0]}:{r.json().get('operations_count')}")
    return out


if __name__ == "__main__":
    print(register(sys.argv[1:] or None))
