"""PriMES 키네틱 데모 초기화 — 데모 그래프(7690)를 비우고, 레지스트리는 PriMES 시스템만 남긴다.

PriMES 자체 데이터는 건드리지 않는다 (시연이 만든 수주·발주·작업지시는 「취소해 줘」 보상으로 되돌린다).
"""
import os
import sys

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "kinetic-mes"))
sys.path.insert(0, HERE)
import seed  # noqa: E402
import systems  # noqa: E402

with seed.driver() as d, d.session() as s:
    s.run("MATCH (n) DETACH DELETE n").consume()
    for c in s.run("SHOW CONSTRAINTS YIELD name WHERE name STARTS WITH 'ont_pub_' RETURN name").value():
        s.run(f"DROP CONSTRAINT `{c}` IF EXISTS").consume()
h = systems.admin_headers()
base = f"{seed.KINETIC_API}/api/kinetic"
for x in httpx.get(f"{base}/systems", headers=h, timeout=20).json():
    if not x["name"].startswith("primes-"):
        httpx.delete(f"{base}/systems/{x['name']}", headers=h, timeout=20)
only = sys.argv[1:] or None
print("registered:", systems.register(only))
httpx.post(f"{base}/catalog/refresh", headers=h, timeout=20)
