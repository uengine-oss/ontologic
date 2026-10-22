"""온보딩 시연 초기화 — 「아무것도 없는 상태」에서 시작한다.

- 데모 그래프(7690)를 **전부** 비운다 — 설비·공장 인스턴스도, 발행 레지스트리도. 온톨로지는 시연 중 구축으로 만든다.
- 서비스 세 곳의 기록을 비운다.
- 레지스트리: mock-mes · mock-aps 는 인증까지 넣어 미리 등록해 두고, **mock-cmms 는 지운다** — 시연에서
  「시스템 등록」 마법사로 OpenAPI 파일을 올려 직접 등록한다. 그 파일은 `onboarding/mock-cmms-openapi.json`.
- Studio 저장소는 `run_studio.sh onboard` 가 새 SQLite 로 바꾼다.
"""

import json
import os
import sys

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import seed  # noqa: E402

with seed.driver() as d, d.session() as s:
    s.run("MATCH (n) DETACH DELETE n").consume()
    for c in s.run("SHOW CONSTRAINTS YIELD name WHERE name STARTS WITH 'ont_pub_' RETURN name").value():
        s.run(f"DROP CONSTRAINT `{c}` IF EXISTS").consume()
seed.reset_services()

admin = seed.token("admin", ["kinetic_admin"])
h = {"Authorization": f"Bearer {admin}"}
base = f"{seed.KINETIC_API}/api/kinetic"
for name, _, svc, desc in seed.SYSTEMS:
    if name == "mock-cmms":
        httpx.delete(f"{base}/systems/{name}", headers=h, timeout=20)
        continue
    httpx.post(f"{base}/systems", headers=h, timeout=20, json=seed.system_body(name, svc, desc)).raise_for_status()
httpx.post(f"{base}/catalog/refresh", headers=h, timeout=20)

# 시연에서 업로드할 OpenAPI 파일 — 서비스가 내놓는 스펙 그대로 (업무 API 만, 숨은 GET /work-orders/{id} 는 없다)
spec = httpx.get(f"{seed.MOCK_CMMS}/openapi.json", timeout=10).json()
out = os.path.join(HERE, "..", "onboarding", "mock-cmms-openapi.json")
with open(out, "w") as f:
    json.dump(spec, f, ensure_ascii=False, indent=2)
systems = [x["name"] for x in httpx.get(f"{base}/systems", headers=h, timeout=20).json()]
print(f"onboard reset: graph empty · services cleared · registry={systems} · spec → {os.path.relpath(out)}")
