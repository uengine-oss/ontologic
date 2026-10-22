"""촬영 전 초기화 — 설비 상태를 RUNNING 으로, 세 서비스(MES·CMMS·APS) 기록을 비운다. 정의·발행은 그대로 둔다."""
import os
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import seed  # noqa: E402

with seed.driver() as d, d.session() as s:
    n = s.run("MATCH (e:Equipment {demo:'kinetic-mes'}) SET e.status = 'RUNNING' RETURN count(e) AS n").single()["n"]
seed.reset_services()
print(f"reset: {n} equipment RUNNING, mock-mes·mock-cmms·mock-aps cleared")
