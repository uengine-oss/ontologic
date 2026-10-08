# Ontology Studio 데스크톱 배포 — 메모리 실측 (2026-08-02)

`ontology-studio-strategy.md` §4-1이 "8GB RAM 미만 로컬 실행"을 미검증 주장으로 남긴 것을
실측으로 확인한 결과다. **이 문서의 숫자는 전부 실측이거나, 실측이 아니면 "미측정/미확인"으로
명시했다.** 추정치는 없다.

## 측정일 · 측정 머신

| 항목 | 값 | 확인 명령 |
|---|---|---|
| 측정일 | 2026-08-02 | — |
| 총 RAM | 128 GB (137,438,953,472 bytes) | `sysctl hw.memsize` |
| CPU | Apple M4 Max, 16코어 | `sysctl -n machdep.cpu.brand_string`, `sysctl -n hw.ncpu` |
| OS | macOS 26.0.1 (Build 25A362) | `sw_vers` |
| 컨테이너 런타임 | Docker Desktop (VM: `com.docker.virtualization`, 설정 16384 MiB / 16 CPU, 실사용 가능 15.6 GiB) | `docker system info`, `ps aux \| grep com.docker.virtualization` |

**중요한 제약**: 이 머신은 목표인 "8GB 머신"이 아니라 128GB 머신이다. 따라서 여기서는
**절대 사용량(컨테이너·프로세스별 RSS/cgroup 사용량)만 실측**하고, "8GB에서 성립하는가"는
그 실측치를 8GB 예산에 대입해 판단한다(§6). 실측치 자체는 머신의 총 RAM 크기와 무관하게
유효하다(컨테이너 cgroup 메모리는 호스트 여유 메모리에 비례해 자동으로 늘어나지 않는다 —
단, Neo4j 기본 힙/페이지캐시는 예외이며 이 머신은 §5에서 확인하듯 명시적으로 고정되어 있다).

---

## 1. 시작 시점 상태

`docker ps -a`, `ps aux | grep -E 'uvicorn|python|mindsdb'`, `lsof -nP -iTCP -sTCP:LISTEN`로 확인.

| 구성요소 | 시작 전 상태 |
|---|---|
| neo4j (robo-neo4j) | **떠 있음** (4일 전부터, healthy) |
| mindsdb (robo-mindsdb) | **떠 있음** (4일 전부터, healthy) |
| postgres (robo-postgres) | **떠 있음** (4일 전부터, healthy) |
| mysql (robo-mysql-sample) | **떠 있음** (4일 전부터, healthy) |
| data-fabric (8004) | **안 떠 있음** — 호스트 프로세스 없음, 포트 리슨 없음 |
| neo4j-text2sql (8020) | **안 떠 있음** |
| ontology-studio backend (8010) | **안 떠 있음** |
| ontology-studio MCP (8100) | **안 떠 있음** |

같은 Docker VM 안에 이 측정과 무관한 다른 프로젝트(process-gpt)의 컨테이너들도 다수
떠 있었다(`supabase-*`, `docker-infra-litellm-*`, `docker-infra-age-postgres-1` 등, 전부
kill하지 않음). **이 때문에 "Docker VM 전체 사용량"은 ontologic 스택만의 순수 사용량이
아니다** — VM 내부 `free -m` 총사용량(10,787 MB, §5 참조)에는 다른 프로젝트 컨테이너
사용량이 섞여 있다. 그래서 이 문서는 VM 전체 사용량이 아니라 **컨테이너별 `docker stats`**
(cgroup 단위, 다른 컨테이너와 격리됨)를 합산 근거로 쓴다.

---

## 2. 기동

`installation.md` §8 "서비스 재기동 방법"과 이슈 #17에 따라 아래를 순서대로 기동했다.
포트 충돌이 없어 재매핑 없이 문서에 적힌 포트 그대로 썼다. 아무것도 kill하지 않았다.

```bash
# data-fabric
cd data-fabric/backend && nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8004 &

# neo4j-text2sql
cd neo4j-text2sql && nohup uv run uvicorn app.main:app --host 0.0.0.0 --port 8020 &

# ontology-studio backend (sandbox 컨테이너 'deepagents-sandbox' 없음 → SANDBOX_BACKEND=local, 이슈 #17)
cd ontology-studio && SANDBOX_BACKEND=local nohup uv run uvicorn backend.src.host.main:app --host 127.0.0.1 --port 8010 &

# ontology-studio MCP (HTTP transport)
cd ontology-studio && MCP_TRANSPORT=http MCP_PORT=8100 nohup uv run ontology-studio-mcp &
```

전부 정상 기동 확인:
- `curl http://127.0.0.1:8004/health` → `{"status":"healthy"}`
- `curl http://127.0.0.1:8020/health` → `{"status":"healthy","neo4j":"connected",...}`
- `curl http://127.0.0.1:8010/docs` → HTTP 200
- MCP: `lsof -nP -iTCP -sTCP:LISTEN | grep 8100` → 리슨 확인

**기동하지 못한 구성요소는 없다.** 필수 8개(컨테이너 4 + 프로세스 4) 전부 이 머신에서 떴다.
Electron 셸만 별도 사유로 미측정(§4).

---

## 3. 유휴(idle) 상태 측정

### 3-1. 컨테이너 (cgroup 기준, `docker stats --no-stream`)

```bash
docker stats --no-stream --format '{{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}'
```

| 컨테이너 | MemUsage | MemPerc (/15.6GiB) |
|---|---|---|
| robo-neo4j | 1.795 GiB | 11.49% |
| robo-mindsdb | 1.06 GiB | 6.80% |
| robo-mysql-sample | 487.7 MiB | 3.05% |
| robo-postgres | 35.82 MiB | 0.22% |
| **소계** | **≈ 3.366 GiB (3447 MiB)** | |

(참고: `deepagent-sandbox-localhost` 컨테이너도 떠 있었으나(764 KiB, 4일 전 실행, 이번
측정과 무관 — ontology-studio backend는 `SANDBOX_BACKEND=local`로 띄워 이 컨테이너를 쓰지
않았다) 필수 4종에 포함하지 않았다.)

### 3-2. 호스트 프로세스 (RSS, `ps -o pid,rss,comm -p <pid>`, KB 단위)

```bash
ps -o pid,rss,comm -p <data-fabric_pid>,<text2sql_pid>,<ontology-backend_pid>,<mcp_pid>
```

| 프로세스 | PID | RSS (idle) |
|---|---|---|
| data-fabric (8004) | 11261 | 102,400 KB ≈ 100.0 MiB |
| neo4j-text2sql (8020) | 11282 | 219,984 KB ≈ 214.8 MiB |
| ontology-studio backend (8010) | 11489 | 189,344 KB ≈ 184.9 MiB |
| ontology-studio MCP (8100) | 12030 | 107,472 KB ≈ 105.0 MiB |
| **소계** | | **≈ 0.591 GiB (604.7 MiB)** |

### 3-3. Docker VM 자체의 호스트 점유 (별도 항목 — 실제 사용자 RAM을 먹는 부분)

```bash
ps aux | grep -iE 'com\.docker|docker desktop|com\.docke' | grep -v grep
```

Docker Desktop 관련 호스트 프로세스(GUI 앱 + 백엔드 + 가상화 헬퍼 + build 데몬 + vmnetd)의
RSS 합계:

| 프로세스 | RSS |
|---|---|
| com.docker.backend ×3 (665,440 / 89,792 / 99,296 KB) | 854,528 KB |
| Docker Desktop (Electron GUI, main+network+GPU helper) | 444,800 KB |
| com.docker.virtualization | 81,232 KB |
| com.docker.build | 72,096 KB |
| com.docker.vmnetd (root) | 13,008 KB |
| **합계** | **1,465,664 KB ≈ 1.398 GiB (1.50 GB)** |

이 값은 **`docker stats`에 잡히지 않는다** — `docker stats`는 VM 내부 cgroup 기준이고, 이
1.4GiB는 macOS 호스트에서 Docker Desktop 앱/데몬/가상화 계층이 그 자체로 먹는 RAM이다.
데스크톱 배포에서 Docker Desktop을 그대로 쓴다면 **이 오버헤드가 고스란히 사용자 RAM에서
빠진다.** (`robo-architect/desktop`이 Docker 대신 Podman을 선택한 이유가 바로 이것 — README:
"no dockerd holding memory".)

참고로 같은 머신에 이미 떠 있던 `robo-architect` 전용 Podman 머신은 `vfkit --memory 6144`로
**6GiB VM을 설정**해 두고 있었다(`ps aux | grep vfkit`로 확인, 실사용량이 아니라 **설정 상한**).
Podman이 Docker Desktop보다 항상 가볍다고 단정할 근거는 이 측정만으로는 없다 — VM 메모리
상한을 얼마로 잡느냐에 달려 있고, 이 값은 이번 측정 대상이 아니었다(미확인).

### 3-4. 유휴 소계

| 구성 | 값 |
|---|---|
| 컨테이너 4종 (§3-1) | 3.366 GiB |
| 호스트 프로세스 4종 (§3-2) | 0.591 GiB |
| **VM 오버헤드 제외 합계** | **3.957 GiB (≈ 4.25 GB)** |
| Docker Desktop 호스트 오버헤드 (§3-3) | 1.398 GiB |
| **VM 오버헤드 포함 합계** | **5.355 GiB (≈ 5.75 GB)** |

---

## 4. 부하(load) 상태 측정

`installation.md` §7의 정식 질의 경로로 2건을 태웠다:

1. `POST /text2sql/react` (8020) — `manufacturing` 데이터소스, "등록된 제품이 모두 몇 개인지
   알려줘" → 정상 응답(`product_count: 10`, MindsDB 실행 9.36ms — 컨텍스트 캐시가 이미
   데워진 상태였음, 최초 콜드스타트가 아님).
2. `POST /api/graph/nl-query` (8010, ontology-studio backend) — `insurance` 데이터소스 질의
   → LLM 호출 400 에러로 실패했지만(별개 문제, 이 측정과 무관), Neo4j/MindsDB 커넥션은
   실제로 소비했다.

각 질의 진행 중 3~5초 간격으로 `docker stats --no-stream`을 3~5회 샘플링했다.

### 4-1. 피크 값

| 컨테이너 | idle | peak (관측) | 증가분 |
|---|---|---|---|
| robo-neo4j | 1.795 GiB | 1.795 GiB | 0 (변화 없음) |
| robo-mindsdb | 1.06 GiB | 1.091 GiB | +31.7 MiB |
| robo-mysql-sample | 487.7 MiB | 493.2 MiB | +5.5 MiB |
| robo-postgres | 35.82 MiB | 37.31 MiB | +1.5 MiB |
| **소계** | 3.366 GiB | **3.404 GiB** | +38.7 MiB |

| 호스트 프로세스 | idle RSS | peak RSS | 증가분 |
|---|---|---|---|
| data-fabric | 100.0 MiB | 100.0 MiB | 0 (이 부하 경로는 data-fabric을 거치지 않음) |
| text2sql | 214.8 MiB | 215.8 MiB | +1.0 MiB |
| ontology-studio backend | 184.9 MiB | 188.6 MiB | +3.7 MiB |
| MCP | 105.0 MiB | 105.0 MiB | 0 (이 부하 경로에서 MCP는 사용 안 됨) |
| **소계** | 604.7 MiB | **609.3 MiB** | +4.7 MiB |

**솔직한 관찰**: 이번에 태운 부하(단발 COUNT 질의 1건 + 실패한 그래프 질의 1건)에서는
컨테이너·프로세스 메모리가 idle 대비 **거의 늘지 않았다**(합계 +43 MiB, 1% 남짓). 이는
①질의가 가볍고(단순 COUNT, 조인 없음) ②MindsDB 컨텍스트 캐시가 이미 데워져 있어
콜드스타트 비용이 빠졌기 때문일 가능성이 높다. **동시 다중 질의, 콜드스타트, 대용량 조인
등 더 무거운 부하에서의 피크는 이번 측정 범위 밖이며 미측정이다.** 사업 결론에는 이 한계를
반영해야 한다 — "부하 시에도 idle과 비슷하다"고 일반화하면 안 된다.

### 4-2. 부하 소계

| 구성 | 값 |
|---|---|
| 컨테이너 4종 peak | 3.404 GiB |
| 호스트 프로세스 4종 peak | 0.595 GiB |
| **VM 오버헤드 제외 합계** | **3.999 GiB (≈ 4.29 GB)** |
| Docker Desktop 호스트 오버헤드 (idle과 동일하다고 가정 — 이 계층은 우리 워크로드와 무관하게 상시 상주) | 1.398 GiB |
| **VM 오버헤드 포함 합계** | **5.397 GiB (≈ 5.80 GB)** |

---

## 5. 감량 여지 조사 (측정 근거 기반)

### 5-1. Neo4j

```bash
docker exec robo-neo4j env | grep -i NEO4J
```

**전략 문서의 가정("힙/페이지캐시를 명시하지 않으면 호스트 RAM 비례로 잡는다")은 이 배포에서는
틀렸다 — 이미 명시적으로 고정되어 있다.** `infra/docker-compose.robo-stack.yml:35-37`:

```yaml
NEO4J_server_memory_heap_initial__size: 512m
NEO4J_server_memory_heap_max__size: 1G
NEO4J_server_memory_pagecache_size: 512m
```

즉 힙 1G + 페이지캐시 512m = 1.5G가 상한이고, 실측 사용량(1.795 GiB)은 여기에 JVM
자체 오버헤드(스레드 스택, 메타스페이스, 네이티브 버퍼 등 ≈ 280MB)를 더한 값과 일치한다.
`docker exec robo-neo4j neo4j-admin server memory-recommendation`로 확인한 **미설정 시
기본 권장값**(이 VM의 15.6GiB 기준)은 힙 5100m + 페이지캐시 6900m로, 지금 설정이 그 대비
**약 4.5배 적게 잡혀 있다** — 이미 상당히 감량된 상태다. 여기서 더 줄이려면(예: 힙 512m,
페이지캐시 256m) 실측 없이는 안전한지 판단 불가(미확인) — 대량 그래프 질의 시 GC 압박이나
페이지캐시 미스 증가로 오히려 느려질 수 있다.

### 5-2. MindsDB

```bash
docker exec robo-mindsdb sh -c "ls /venv/lib/python3.10/site-packages/mindsdb/integrations/handlers | wc -l"
docker exec robo-mindsdb sh -c "du -sh /venv/lib/python3.10/site-packages/mindsdb/integrations/handlers"
docker exec robo-mindsdb ps aux --sort=-rss
```

- 핸들러 **218개**가 설치되어 있고, 소스 코드 전체 용량은 **14MB**뿐이다.
- 실제 메모리(1.06~1.09 GiB)는 핸들러 코드가 아니라 **4개의 멀티프로세싱 워커
  프로세스**(각 190~380MB RSS)와 메인 프로세스(~180MB)에서 나온다 — 이는 Python
  런타임 + 로드된 라이브러리(pandas/numpy 등 추정되나 개별 확인은 안 함) 비용이다.

**결론(측정 근거)**: "필요한 핸들러만 남긴 커스텀 빌드"는 근거가 약하다. 핸들러 소스
용량 자체가 전체의 1% 수준(14MB/1.06GB)이라, 핸들러를 다 빼도 코드 크기 절감은
미미하다. 실효 있는 절감이 있다면 그건 핸들러 제거가 아니라 **워커 프로세스 수 조정**
(`MINDSDB_...WORKERS` 류 설정 확인 필요 — 이번에 확인 못함, 미확인) 쪽일 가능성이 크다.
이 부분은 추가 실측이 필요하다.

### 5-3. PostgreSQL / MySQL

```bash
docker exec robo-postgres psql -U postgres -c "SHOW shared_buffers;"
docker exec robo-mysql-sample mysql -uroot -prootpass123 -e "SHOW VARIABLES LIKE 'innodb_buffer_pool_size';"
```

| DB | 현재값 | 출처 |
|---|---|---|
| Postgres `shared_buffers` | 128MB | 이미지 기본값 — `infra/docker-compose.robo-stack.yml`의 `postgres` 서비스에 관련 설정 없음(직접 확인) |
| MySQL `innodb_buffer_pool_size` | 128MB (134,217,728 bytes) | 이미지 기본값 — 마찬가지로 compose에 설정 없음 |

두 값 다 이미 작다(각 128MB). 실측 사용량(postgres 36MB대, mysql 488MB대)을 보면
**postgres는 버퍼풀보다도 적게 쓰고 있어 감량 여지가 없다.** mysql은 488MB 중
버퍼풀(128MB)이 27%뿐이라 — 나머지는 MySQL 서버 자체의 스레드/커넥션/InnoDB 로그
오버헤드로 추정되나 정확한 내역은 미확인.

**추가 발견(감량과 무관하지만 중요)**: `mysql-sample`은 compose에 `platform: linux/amd64`로
고정되어 있어, 이 Apple Silicon(arm64) 머신에서 **QEMU 에뮬레이션으로 실행 중**이다
(`docker exec robo-mysql-sample uname -m` → `x86_64`, 반면 neo4j/mindsdb/postgres는
`aarch64`로 네이티브 실행 확인). 에뮬레이션이 메모리를 얼마나 더 먹는지는 이번 측정으로는
분리 불가(같은 이미지의 arm64 네이티브 버전과 비교해야 함 — 미확인)지만, **CPU 오버헤드는
`installation.md` 이슈 #12(ANTLR 파서 QEMU)에서 이미 "시스템 전체를 마비시킬 정도"로
확인된 전례가 있어 무시할 문제는 아니다.** `mysql:8.0`의 arm64 네이티브 이미지로 교체하는
것을 감량 여지가 아니라 **안정성 개선**으로 별도 트래킹할 것을 권한다.

---

## 6. Electron 셸 — 미측정 (사유 포함)

`ontology-studio`에는 아직 Electron 셸이 없다. 참고값으로 `robo-architect/desktop`의
패키징된 앱(`dist/mac-arm64/Robo-Architect.app`)을 직접 실행해 측정을 시도했다:

```bash
open -a /Users/uengine/robo-architect/desktop/dist/mac-arm64/Robo-Architect.app
# 그리고 바이너리 직접 실행도 시도
/Users/uengine/robo-architect/desktop/dist/mac-arm64/Robo-Architect.app/Contents/MacOS/Robo-Architect
```

**두 방식 모두 프로세스가 뜨지 않고(또는 즉시 종료 코드 0으로 종료) 실패했다.** 이 세션은
GUI 세션(WindowServer)에 연결되지 않은 비대화형 환경이라 Electron/Chromium이 렌더링할
디스플레이가 없어서로 판단된다(에러 메시지 없이 조용히 종료 — 전형적인 headless 환경의
Electron 동작). 이 문서의 다른 모든 측정은 CLI/HTTP 기반이라 문제없었지만, GUI 앱은 이
환경의 구조적 한계로 실측이 불가능했다.

**대안으로 이미 이 머신에서 돌고 있던 "유사 Electron 앱"인 Docker Desktop을 참고 측정**했다
(§3-3의 세부 항목):

| 프로세스 | RSS |
|---|---|
| Docker Desktop (main, `--reason=open-tray`, 즉 창 없이 트레이만) | 277,280 KB |
| Docker Desktop Helper (network utility) | 60,848 KB |
| Docker Desktop Helper (GPU) | 106,640 KB |
| **합계** | **444,768 KB ≈ 434 MiB** |

**이 434 MiB는 실제 Electron 셸 오버헤드의 하한선일 뿐이다 — 명시적으로 과소평가다.**
이 순간 Docker Desktop은 `--reason=open-tray`로 **창이 열려 있지 않은 상태**였다. 실제
사용자가 앱 창을 열면 Renderer 프로세스(SPA 렌더링 담당, 보통 GPU/utility 프로세스보다
크다)가 추가로 뜨는데 이번 관측 시점에는 그 프로세스가 없었다. ontology-studio Electron
셸이 만들어지면 프론트(Vue 3 SPA)를 실제로 창에 띄운 상태로 **반드시 재측정**해야 한다.

---

## 7. 결론

### 7-1. 합계 (이 머신 실측, 128GB 머신 기준 절대값 — 머신 RAM 크기와 무관하게 유효)

| 시나리오 | 컨테이너 4종 + 호스트 프로세스 4종 | + Docker Desktop VM 오버헤드 | + Electron (미측정, 하한선만) |
|---|---|---|---|
| idle | 3.957 GiB | 5.355 GiB | 5.355 GiB + (≥0.434 GiB, 미측정 하한) |
| peak (경량 질의 1건) | 3.999 GiB | 5.397 GiB | 5.397 GiB + (≥0.434 GiB, 미측정 하한) |

### 7-2. 8GB 머신에서 성립하는가 — **아니오 (측정 근거로 판단)**

과제 지시대로 8GB 머신은 OS가 이미 2~3GB를 쓴다고 가정한다.

- **VM 오버헤드 포함, 최선의 경우(Podman으로 교체해 Docker Desktop 1.4GiB를 없앤다고
  가정해도)**: idle 3.957 GiB + OS 2~3 GiB = **5.96~6.96 GiB**. 8GB 안에 들어오지만
  Electron 창을 하나도 안 띄운 상태(그냥 백엔드 스택만)에서 이미 이 정도이고, 부하나
  Electron 셸을 더하면 여유가 거의 없다.
- **이번에 실제로 측정한 대로(Docker Desktop 그대로, VM 오버헤드 포함)**: idle 5.355 GiB
  + OS 2~3 GiB = **7.36~8.36 GiB**. 이미 8GB 경계에 걸치거나 넘는다 — **그런데 이 숫자는
  Electron 셸(미측정, 하한선만 잡아도 +0.43 GiB 이상, 창을 띄우면 더 큼)을 전혀 포함하지
  않은 값이다.** Electron을 더하면 확실히 8GB를 넘긴다.
- 부하 상태(피크)는 idle 대비 소폭 증가(+43 MiB, 이번 경량 질의 기준)했지만, **콜드스타트나
  동시 질의 같은 더 무거운 부하는 측정하지 못했다** — 실제 피크는 이보다 클 수 있다.

**결론: 아니오.** 이번 실측 범위(Docker Desktop, 경량 질의 1건, Electron 미포함)만으로도
이미 8GB 예산이 빡빡하거나 초과하며, 측정하지 못한 항목(무거운 부하 피크, Electron 실측치)
전부가 **합계를 늘리는 방향**이라 실제 상황은 이보다 나쁠 가능성이 높다.

### 7-3. 감량안을 적용하면?

- Neo4j 힙/페이지캐시는 **이미 15.6GiB 기준 기본값 대비 4.5배 감량된 상태** — 추가
  감량은 실측 없이는 안전성을 보장 못 한다(§5-1).
- MindsDB 커스텀 빌드(핸들러 제거)는 **근거가 약하다** — 핸들러 소스가 전체 용량의 1%뿐
  이라 절감 효과가 크지 않을 것으로 보인다(§5-2). 워커 프로세스 수 조정은 미확인이지만
  더 유망한 방향이다.
- Docker Desktop → Podman 전환(robo-architect 방식)이 **가장 확실한 감량 레버**다: VM
  오버헤드 1.4 GiB 중 상당 부분(Docker Desktop 고유의 Electron GUI + 다중 백엔드 프로세스)
  을 없앨 수 있다. 다만 Podman 자체도 VM을 쓰므로 오버헤드가 0이 되지는 않는다(§3-3 —
  robo-architect의 Podman 머신은 6144MB **상한**으로 설정되어 있었다, 실사용량 미측정).
- Postgres/MySQL 버퍼는 이미 작아서(각 128MB) 감량 여지가 거의 없다(§5-3).

**그래도 8GB에서 안 되면 무엇을 포기해야 하는가**: 위 감량을 다 적용해도(Neo4j는 이미
한계에 가깝고, MindsDB/DB 2종은 절감 여지가 작음) 이론적 최선의 경우도 OS 2~3GB를 빼면
Electron+부하 여유가 1GB 남짓뿐이다. 8GB를 확실히 지키려면 다음 중 하나를 포기해야 할
가능성이 높다: ①MindsDB(경량 데이터소스 페더레이션을 자체 구현으로 대체), 또는
②"모든 필수 구성요소가 항상 상주" 원칙을 깨고 온디맨드 기동/종료로 바꾸는 것. 이 두
방향 모두 실측 없이 결정할 사안이 아니며, 다음 재측정 라운드의 대상이다.

---

## 8. 재측정 방법

나중에 다시 재려면:

1. **환경 확인**: `docker ps -a --format '{{.Names}}\t{{.Status}}'`로 4개 컨테이너
   (neo4j/mindsdb/postgres/mysql-sample) 살아있는지 확인. 없으면 `installation.md` §8
   "서비스 재기동 방법" 그대로.
2. **호스트 프로세스 기동**: `installation.md` §8의 재기동 명령 + 이 문서 §2의
   ontology-studio backend/MCP 기동 명령. PID는 `ps aux | grep uvicorn`으로 확인.
3. **idle 측정**: 기동 후 최소 1분 대기(초기 인덱싱/캐시 워밍 끝날 때까지) 후
   `docker stats --no-stream`과 `ps -o pid,rss,comm -p <pid1>,<pid2>,...`.
4. **VM 오버헤드**: `ps aux | grep -iE 'com\.docker|docker desktop|com\.docke'`
   (Podman이면 `ps aux | grep -iE 'podman|vfkit|gvproxy'`)의 RSS 합.
5. **peak 측정**: `installation.md` §7의 `/text2sql/react` 질의(가능하면 **콜드스타트
   상태**로 — 서비스 막 기동한 직후, 이번 측정처럼 캐시 데워진 상태 말고)를 쏘면서
   3~5초 간격 `docker stats --no-stream` 3~5회. 더 정확한 피크를 보려면
   `tests/e2e/test_pipeline_api.py`를 동시에 여러 개 병렬 실행하거나 `hey`/`ab` 같은
   부하 도구로 `/text2sql/react`에 동시 요청 5~10개를 태울 것 — 이번 측정에서 못 한 부분.
6. **Electron**: GUI 세션이 있는 일반 데스크톱 터미널(비대화형 CLI 에이전트가 아닌 환경)
   에서 `open /Users/uengine/robo-architect/desktop/dist/mac-arm64/Robo-Architect.app`로
   실행하고 **창을 띄운 상태**에서 `ps aux | grep -i "Robo-Architect"`로 main + renderer +
   GPU 헬퍼 RSS 합을 잰다. ontology-studio 자체 Electron 셸이 생기면 그걸로 대체 측정.
7. **8GB 판단**: 위 합계 + VM 오버헤드 + Electron + OS 2~3GB를 더해 8GB와 비교. 이 문서의
   §7-2 계산식을 새 숫자로 그대로 대입하면 된다.

---

## 9. 추가 측정 — **ANTLR 코드 파서를 core 팩에 넣은 이후** (2026-08-03)

§1~§8 은 core 팩이 **neo4j · mindsdb · data-fabric · neo4j-text2sql** 넷이던 시점의
측정이다. 그 뒤 「메타데이터 증강」의 코드 분석을 실제로 동작시키기 위해 **ANTLR 코드
파서(8081)** 가 core 팩에 들어왔다. 위 숫자를 덮어쓰지 않고 여기에 따로 적는다.

### 9-1. 측정 조건 (§측정 조건과 다르다 — 비교할 때 주의)

| 항목 | 값 |
|---|---|
| 측정일 | 2026-08-03 |
| 머신 | 같은 머신 (Apple M4 Max, 128GB, macOS 26.0.1) |
| 컨테이너 런타임 | **Podman** (`podman machine ontology-studio`, **6144 MB** 상한) — §1~§8 은 Docker Desktop(15.6 GiB)이었다 |
| 측정 명령 | `CONTAINER_CONNECTION=ontology-studio podman stats --no-stream` · 컨테이너 안에서 `/proc/1/status` 의 `VmRSS` |

**런타임이 다르므로 §3-1 표와 컨테이너별 숫자를 직접 빼서 비교하면 안 된다.** 아래
9-3 은 이번 라운드 안에서만 비교한다.

### 9-2. ANTLR 파서 하나의 힙 설정별 실측 — 이것이 이번 라운드의 본론

서브모듈 `antlr-code-parser/Dockerfile` 의 ENTRYPOINT 는 `-Xms512m -Xmx4096m` 이다.
**최대 힙 4GB 는 podman machine 총 메모리(6144MB)의 2/3** 라서 그대로 둘 수 없었다.
설정별로 재 봤다 (모두 기동 직후 유휴, 같은 이미지 `localhost/ontology-studio/antlr-parser:local`):

| 설정 | 적용 방법 | 유휴 RSS | 비고 |
|---|---|---|---|
| `-Xms512m -Xmx4096m` | 서브모듈 Dockerfile 원본 | **483,464 kB (472 MiB)** | 기준선 |
| `-Xms128m -Xmx1024m` | `JAVA_TOOL_OPTIONS` | 477,784 kB (467 MiB) | **거의 안 줄었다** — 아래 참조 |
| `-Xms256m -Xmx2048m` | entrypoint 교체 | 417,828 kB (408 MiB) | |
| `-Xms128m -Xmx4096m` | entrypoint 교체 | 345,556 kB (338 MiB) | 최대 힙은 유휴에 거의 영향 없음 |
| **`-Xms128m -Xmx1536m`** | **entrypoint 교체 (채택)** | **351,972 kB (344 MiB)** | 배포 설정 |

읽어야 할 두 가지:

1. **유휴 RSS 를 정하는 것은 `-Xmx` 가 아니라 `-Xms` 다.** `-Xms512m` → `-Xms128m` 하나로
   472 MiB → 338~344 MiB, **약 130 MiB(-28%)** 가 줄었다. `-Xmx` 를 4096m 에서 1536m 으로
   내린 것은 유휴 사용량을 사실상 바꾸지 않는다(최대 힙은 예약일 뿐 커밋이 아니다).
2. **`JAVA_TOOL_OPTIONS` 로는 낮출 수 없다.** 컨테이너는 `Picked up JAVA_TOOL_OPTIONS:
   -Xms128m -Xmx1024m` 을 찍고도 RSS 가 그대로였다. `JAVA_TOOL_OPTIONS` 는 명령줄 **앞에**
   붙고 HotSpot 은 중복 플래그에서 **뒤엣것**을 쓰므로, Dockerfile 의 `-Xms512m -Xmx4096m`
   이 이긴다. 그래서 compose 에서 `entrypoint` 를 교체했다(서브모듈은 고치지 않는다).

### 9-3. 그럼 `-Xmx` 는 왜 내렸는가 — OOM 의 **대상**이 달라진다

유휴에 영향이 없다면 최대 힙은 그냥 크게 둬도 되지 않느냐는 반론이 성립한다. 성립하지
않는 이유를 실측했다.

`-Xms256m -Xmx2048m` 상태에서 **87,919줄짜리 생성 자바 파일**(ANTLR 이 만든
`PostgreSQLParser.java`)을 파싱시키자 컨테이너가 죽었다:

```
podman inspect -f '{{.State.ExitCode}} {{.State.OOMKilled}}'  →  137 true
```

이때 죽인 것은 **JVM 이 아니라 VM 의 커널**이다. podman machine 은 6144MB 이고 코어 팩이
이미 2.4GB 를 쓰고 있어, 힙이 실제로 자라면 VM 이 먼저 고갈된다. 그 상황에서 커널이
고르는 희생자가 **파서라는 보장이 없다** — neo4j 가 죽으면 사용자는 "코드 분석을 눌렀더니
그래프 DB 가 끊겼다" 를 겪는다.

힙을 1536m 으로 묶으면 같은 입력이 **JVM 안의 `OutOfMemoryError`** 로 끝난다. 파싱
스트림이 `error` 이벤트로 실패하고 나머지 스택은 살아 있다. 즉 이 값은 "얼마나 큰 파일을
파싱할 수 있는가" 와 "실패했을 때 누가 죽는가" 의 교환이고, 데스크톱에서는 후자가 훨씬
중요하다고 판단했다.

**대신 조절 가능하게 뒀다** — 큰 코드베이스를 다루는 사용자는 compose 환경변수로 올릴 수
있다: `ONTOLOGY_STUDIO_ANTLR_HEAP_INITIAL`(기본 `128m`) ·
`ONTOLOGY_STUDIO_ANTLR_HEAP_MAX`(기본 `1536m`).

### 9-4. 파싱 후에도 돌아오지 않는다 (작은 입력 기준)

파이썬 4개 파일(77줄)을 「분석 시작」으로 파싱한 뒤:

| 시점 | RSS |
|---|---|
| 기동 직후 유휴 | 351,972 kB (344 MiB) |
| 파싱 직후 | 382,892 kB (374 MiB) |
| 파싱 4분 뒤 (유휴) | 383,004 kB (374 MiB) |

작은 입력에도 **+30 MiB 가 붙고 그대로 남는다**(JVM 은 커밋한 힙을 잘 반납하지 않는다).
컨테이너를 재시작하면 344 MiB 로 돌아간다. 즉 **오래 켜 둔 세션의 파서는 유휴 344 MiB 가
아니라 그보다 큰 값으로 봐야 한다.** 큰 코드베이스에서 얼마나 커지는지는 **측정하지
않았다**(위 OOM 실험 외에는 대규모 입력을 재지 않았다).

### 9-5. 이번 라운드 전체 스냅샷 (Podman, 이 머신, 유휴)

`podman stats --no-stream`, 예제 데이터 팩 ON, 파서는 4파일 파싱을 한 번 마친 상태.

| 컨테이너 | 사용량 |
|---|---|
| neo4j | 885.4 MB |
| mindsdb | 976.4 MB |
| **antlr (신규)** | **394.2 MB** |
| neo4j-text2sql | 140.9 MB |
| data-fabric | 79.2 MB |
| **core 소계** | **2,476.1 MB ≈ 2.36 GiB** |
| sample-mysql | 417.8 MB |
| sample-postgres | 38.8 MB |
| **sample 소계** | **456.6 MB ≈ 0.44 GiB** |
| **합계** | **2,932.7 MB ≈ 2.80 GiB** |

**ANTLR 추가로 core 팩이 늘어난 몫은 약 344~394 MB (유휴~파싱 후) = core 소계의 약 16%다.**
Dockerfile 원본 설정 그대로였다면 이 자리가 472 MiB 였다.

### 9-6. 8GB 판단에 미치는 영향 — **재계산하지 않았다**

§7-2 의 8GB 판단은 Docker Desktop 기준이고 이번 라운드는 Podman 이다. 두 런타임의
VM 오버헤드를 같은 조건에서 재지 않았으므로 §7-2 의 숫자에 이번 344~394 MB 를 그냥
더하는 것은 **틀린 계산**이다. 다만 방향은 분명하다: **core 팩 유휴가 늘었고, 8GB 예산은
§7-2 시점에 이미 빠듯했다.** Podman 기준 전체 재측정(§8 절차를 Podman 으로)은 다음
라운드의 과제로 남는다.

### 9-7. 재측정 방법

```bash
export CONTAINER_CONNECTION=ontology-studio
podman stats --no-stream --format '{{.Name}}\t{{.MemUsage}}'
podman exec ontology-studio-desktop-antlr-1 sh -c "grep -E 'VmRSS|VmHWM' /proc/1/status"

# 힙 설정을 바꿔 가며 재려면 (compose 를 거치지 않고 단독으로)
podman run --rm -e SERVER_PORT=8081 \
  --entrypoint '["java","-Xms128m","-Xmx1536m","-jar","app.jar"]' \
  localhost/ontology-studio/antlr-parser:local
```

유휴 값은 **기동 직후**에 재야 한다(§9-4 — 한 번이라도 파싱하면 돌아오지 않는다).

---

## 10. 추가 측정 — **ROBO 분석기·카탈로그를 호스트 프로세스로 넣은 이후** (2026-08-03)

§9 는 core 팩에 ANTLR 파서가 들어온 시점이다. 그 뒤 「메타데이터 증강」의 **파싱 다음
단계**를 동작시키기 위해 두 서비스가 더 들어왔다:

- **robo-data-analyzer** (선호 18502) — ANTLR JSON → LLM 분석 → Neo4j 적재
- **robo-data-catalog** (선호 18503) — 그래프·스키마·리니지 조회

둘 다 **컨테이너가 아니라 호스트 프로세스**다(근거: `desktop/src/main/robo.js` 머리말).
그래서 이 항목은 §3-1(컨테이너) 이 아니라 **§3-2(호스트 프로세스 RSS)** 와 같은 종류의
숫자다. §9 표를 덮어쓰지 않고 여기에 따로 적는다.

### 10-1. 측정 조건

| 항목 | 값 |
|---|---|
| 측정일 | 2026-08-03 |
| 머신 | 같은 머신 (Apple M4 Max, 128GB, macOS 26.0.1) |
| 실행 형태 | Electron 앱이 띄운 자식 프로세스 (`npm --prefix desktop start`, 개발 체크아웃) |
| 인터프리터 | 각 서브모듈의 `.venv` (CPython 3.12.12) |
| 측정 명령 | `ps -o pid,rss -p <pid>` |
| 상태 | **기동 직후 유휴** — 분석을 한 번도 돌리지 않은 시점 |

### 10-2. 호스트 프로세스 유휴 RSS

| 프로세스 | RSS | 비고 |
|---|---|---|
| ontology-studio backend | 146,416 kB (143.0 MiB) | 기존 (§3-2 와 다른 런타임·다른 날) |
| ontology-studio MCP | 98,496 kB (96.2 MiB) | 기존 |
| **robo-data-catalog (신규)** | **111,856 kB (109.2 MiB)** | FastAPI + neo4j 드라이버 + langchain |
| **robo-data-analyzer (신규)** | **411,040 kB (401.4 MiB)** | ← 아래 |
| **호스트 프로세스 합계** | **767,808 kB ≈ 750 MiB** | |

같은 날 다른 기동에서 다시 재면 카탈로그 **107.0 MiB** · 분석기 **400.0 MiB** 였다.
기동마다 몇 MiB 흔들리므로 소수점 이하는 비교에 쓰지 않는다.

**분석기 401 MiB 의 대부분은 임베딩 스택이다.** `requirements.txt` 가
`sentence-transformers==3.3.1` 을 고정하고 있고 그것이 torch 를 끌고 온다 — 이 서비스의
`.venv` 는 **932 MB** 로, 카탈로그(136 MB)의 7배다. 이 비용은 **import 시점에** 발생한다:
분석을 한 번도 돌리지 않은 유휴 상태에서 이미 401 MiB 다.

`ROBO_PIPELINE_EMBED_ENABLED=false` 로 임베딩 **단계**를 끌 수는 있지만, 그것으로 이
숫자가 줄어드는지는 **측정하지 않았다**(임포트는 단계 실행 여부와 무관할 가능성이 높다).
줄이려면 서브모듈에서 지연 임포트로 바꿔야 하고, 그건 이 작업의 범위 밖이다.

### 10-3. 이 시점의 전체 스냅샷 (유휴, 예제 데이터 팩 ON)

컨테이너는 `podman stats --no-stream`, 호스트 프로세스는 `ps -o rss`.

| 구성요소 | 형태 | 사용량 |
|---|---|---|
| neo4j | 컨테이너 | 912.7 MB |
| mindsdb | 컨테이너 | 914.1 MB |
| antlr | 컨테이너 | 369.1 MB |
| neo4j-text2sql | 컨테이너 | 201.3 MB |
| data-fabric | 컨테이너 | 78.4 MB |
| ontology-studio backend | 호스트 | 149.9 MB |
| ontology-studio MCP | 호스트 | 100.9 MB |
| **robo-data-analyzer** | **호스트** | **420.9 MB** |
| **robo-data-catalog** | **호스트** | **114.5 MB** |
| **core 소계 (컨테이너 5 + 호스트 4)** | | **3,261.8 MB ≈ 3.11 GiB** |
| sample-mysql | 컨테이너 | 374.6 MB |
| sample-postgres | 컨테이너 | 19.7 MB |
| **sample 소계** | | **394.3 MB ≈ 0.38 GiB** |
| **합계** | | **3,656.1 MB ≈ 3.49 GiB** |

MB 는 `podman stats` 표기(10진), kB→MB 환산은 `ps` 값 ÷ 1000. 두 도구의 단위가 다르므로
소수점 이하는 비교에 쓰지 않는다.

**이번 라운드가 core 팩에 더한 몫은 약 535 MB (분석기 421 + 카탈로그 115)**, §9-5 의
core 소계 2,476 MB 대비 **+22%** 다. Electron 셸 자체와 podman machine VM 오버헤드는
여전히 **미측정**이다(§4·§6).

### 10-4. 컨테이너로 넣었다면 더 쌌는가 — **아니다** (근거)

이 둘을 컨테이너에 넣었으면 §3-3 이 기록한 "VM 오버헤드" 쪽으로 옮겨갈 뿐 총량이 줄지
않는다. 오히려:

- 이미지가 커진다 — analyzer 의 의존성만 932 MB 이고, 여기에 베이스 이미지가 더해진다.
- podman machine 은 **6144 MB 상한**이다(§9-1). 지금 컨테이너 소계가 2,890 MB 인데
  여기에 분석기를 넣으면 §9-3 에서 실제로 겪은 **VM 고갈 → 엉뚱한 컨테이너 OOMKill**
  위험대에 더 가까워진다. 호스트 프로세스는 그 상한 밖이다.

즉 호스트 배치는 (파일시스템 공유·디스크 접근이라는 기능적 이유 외에도) **VM 예산을
쓰지 않는다**는 부수 이점이 있다. 다만 이것은 사용자 RAM 총량을 줄이지는 않는다.

### 10-5. 재측정 방법

```bash
# 앱을 띄운 뒤
pgrep -fl "robo-data-(analyzer|catalog)/.venv"
ps -o pid,rss,command -p <pid> ...

export CONTAINER_CONNECTION=ontology-studio
podman stats --no-stream --format '{{.Name}}\t{{.MemUsage}}'
```

유휴 값은 **분석을 한 번도 돌리기 전에** 재야 한다. 분석은 임베딩 모델을 실제로
내려받아 적재하므로 그 뒤의 값은 다른 숫자다(얼마나 커지는지는 **측정하지 않았다** —
이 머신에서 유효한 LLM 키가 없어 분석 단계를 끝까지 돌리지 못했다. §11 evidence README).

---

## 11. 라운드 4 — spec 007 T1~T4 이후 (2026-08-03, 부분 측정)

**결론: 이 변경으로 메모리를 재지 않았다. 약속했던 SC-016 재측정은 미완이다.**
숨기지 않고 무엇을 재고 무엇을 못 쟀는지만 적는다.

### 11-1. 왜 못 쟀는가

이 작업의 검증은 **호스트 프로세스**로 했다 — 데스크톱 스택의 `text2sql`·`data-fabric`
컨테이너 이미지를 다시 굽지 않았기 때문이다(`desktop/scripts/build-images.sh` 미실행).
따라서 §10-3 과 **같은 방법으로** 잰 core 소계 비교값이 없다. 같은 방법이 아닌 숫자를
라운드로 얹으면 이 문서의 비교 가능성이 깨진다.

### 11-2. 그래도 방향을 말할 수 있는 것

| 항목 | 변화 | 근거 |
|---|---|---|
| text2sql 기동 시 **벡터화 잡** | **사라짐**(기본값) | `TEXT2SQL_VECTORIZE_ON_STARTUP` 기본 `true` → `false`. 기동 중 테이블 전수 LLM 프로필 + 임베딩 배치가 돌지 않는다 |
| 임베딩 모델 **적재 벌 수** | **0 벌**(우리 스택 기준) | `EMBEDDING_PROVIDER=llm_endpoint` 로 사용자가 이미 돌리는 서버를 쓴다. 우리 프로세스는 HTTP 클라이언트만 갖는다 |
| 색인 시점 | 기동 → **추출 요청 시** | 유휴 상태의 피크가 기동에서 사라지고, 추출을 누른 시점으로 옮겨간다 |

**AD-5 가 노린 것(임베딩 스택을 한 벌도 새로 들이지 않는다)은 성립한다** —
미결정 11번이 참으로 확인됐기 때문이다(로컬 OpenAI 호환 서버가 `/v1/embeddings` 를 서빙한다).
`local`(번들 400 MB 모델) 제공자는 구현하지 않았으므로 §10-2 가 경고한 `+800 MB, +24.5%`
시나리오는 **아직 발생할 수 없다.**

### 11-3. 재측정할 때 해야 할 것

1. `bash desktop/scripts/build-images.sh` 로 text2sql·data-fabric 이미지를 다시 굽는다.
2. §10-5 의 방법 그대로 유휴값을 잰다 — **추출을 한 번도 돌리기 전에.**
3. 추출(=색인) 중의 피크를 따로 잰다. 이 라운드에서 새로 생긴 부하 지점이다.
   배치 크기는 `TEXT2SQL_VECTOR_EMBED_BATCH_SIZE`(기본 128)가 정한다.
