# Ontology Studio 데스크톱 패키징 — 설계 결정

**작성일** 2026-08-02 · **대상** `ontology-studio/desktop/` (Electron + Podman)
**참고 구현** `/Users/uengine/robo-architect/desktop/` (동작 확인·DMG 산출 완료)

이 문서는 로드맵 작업 4(Electron 패키징)의 **구현 전 결정**을 기록한다. 참고 구현의
결론을 그대로 베끼지 않고, ontology-studio 코드를 읽고 판단한 결과다. 각 결정에 근거
경로를 적었으므로 코드가 바뀌면 같은 경로로 재확인한다.

전제가 되는 두 문서:

- [`ontology-studio-strategy.md`](ontology-studio-strategy.md) §4-1 — 데스크톱에 반드시
  들어가야 하는 구성 9종. **사업 결정이며 협상 대상이 아니다.**
- [`memory-footprint-measurement.md`](memory-footprint-measurement.md) — 실측 idle
  3.96 GiB(컨테이너 4 + 프로세스 4, Docker VM 오버헤드 제외).

---

## 0. 결론 요약

| # | 결정 | 한 줄 근거 |
|---|---|---|
| 1 | **ontology-studio backend·MCP 는 호스트 프로세스**, 나머지는 컨테이너 | 컨테이너에 넣으면 `AGENT_BACKEND=cliagents` 경로가 죽는다 — 데스크톱에서 이건 "API 키 없이 바로 쓴다"를 잃는 것 |
| 2 | data-fabric·neo4j-text2sql 은 **컨테이너**, 이미지는 **서브모듈 소스에서 로컬 빌드** | 배포된 `ghcr.io/uengine-oss/robo-data-fabric` 은 **amd64 전용**(실측 확인) — Apple Silicon 에서 QEMU (이슈 #12 전례) |
| 3 | **core 팩 + sample-data 팩** 2단 구성. sample 은 **기본 ON**, 나중에 끌 수 있음 | §4-1 을 지키면서(첫 실행에 다 뜬다) 자기 DB 를 연결한 사용자에게 0.53 GiB 를 돌려준다 |
| 4 | 사용자 설정은 `<userData>/ontology-studio.env` **하나**. 소스 트리에 `.env` 를 절대 만들지 않는다 | constitution VI. `load_dotenv()` 는 `override=False` 라 **프로세스 env 가 항상 이긴다** |
| 5 | 호스트 공개 포트는 **전부 동적 할당**. 단 MCP 포트만 **sticky**(한 번 정하면 유지) | installation.md 이슈 #1 — 이 머신에서 5432·7474/7687·8000·8010 이 전부 충돌했다. 단 MCP 는 외부 AI 클라이언트가 손으로 적는 주소다 |

---

## 1. 무엇을 컨테이너에 넣고 무엇을 호스트 프로세스로 둘 것인가

### 1-1. 참고 구현의 판단 기준

robo-architect 는 Architect API 를 호스트에 뒀다. README 가 든 이유는
**"사용자 PC 의 레포를 사용자 도구로 다룬다"** 이다 — git worktree, agent CLI, PTY.
그 외(neo4j·analyzer 팩)는 컨테이너다. 기준은 한 문장으로 요약된다:

> 컨테이너 경계를 넘으면 **제품이 무엇인지가 바뀌는** 부분만 호스트에 둔다.

이 기준을 ontology-studio 에 적용하면 답이 자명하지 않다. 확인한 사실은 다음과 같다.

### 1-2. 확인한 사실

| 사실 | 근거 |
|---|---|
| 에이전트 백엔드가 **두 개**다. `AGENT_BACKEND=deepagents`(기본, 인프로세스 LangChain) / `cliagents`(외부 CLI 구동) | `backend/src/modules/agent_session/service.py:781-806`, `shared/kernel/settings.py:132` |
| `cliagents` 는 `shutil.which()` 로 **PATH 에서 `claude`/`codex` 를 찾는다.** 못 찾으면 `AgentNotInstalledError` | `cliagents/src/cliagents/detection.py:46-52`, `provider.py:245-249` |
| 인증은 **CLI 자신의 `$HOME` 상태**(`~/.claude`, `~/.codex`)에 달려 있다. 백엔드는 API 키를 CLI 에 넘기지 않는다 | `cliagents_backend.py:703`, `cliagents/provider.py:127-132`, `.env.example:31-33` |
| 두 Dockerfile 어디에도 **Node.js·`claude`·`codex` 가 설치되지 않는다** | `ontology-studio/Dockerfile`, `backend/Dockerfile` |
| `cliagents` 는 CLI 에 MCP URL 을 `http://127.0.0.1:<BACKEND_PORT>/mcp/agent-bridge/<mode>/` 로 넘긴다 (`0.0.0.0`→`127.0.0.1` 치환) | `cliagents_backend.py:627-633` |
| CLI 는 **권한 우회 플래그로 돈다** — `--permission-mode bypassPermissions` / `--dangerously-bypass-approvals-and-sandbox`. 코드 주석이 "the studio is the sandbox boundary here" 라고 명시 | `cliagents_backend.py:226-229, 380-382` |
| PTY 는 **쓰지 않는다.** `subprocess.Popen` + 파이프. 백엔드 전체에 `pty` import 0건 | `cliagents_backend.py:175-189` |
| 샌드박스 백엔드도 두 개다. `SANDBOX_BACKEND=docker`(기본) / `local` | `shared/sandbox/__init__.py:13-41` |
| `docker_backend` 는 **`docker` 바이너리 이름을 하드코딩**한다 (`docker inspect/exec/cp`). `files/workspace.py` 도 마찬가지 — 합계 14개 호출 지점 | `shared/sandbox/docker_backend.py:40,77,120,157,177`, `modules/files/workspace.py:70,129,136,192,223,243,267,292` |
| 부팅 시 샌드박스 준비 검사가 **fail-fast** 다. 어긋나면 백엔드가 아예 안 뜬다 | `service.py:847-867`, installation.md 이슈 #17 |
| 에이전트 작업공간은 사용자의 프로젝트가 **아니다.** `LOCAL_SANDBOX_ROOT`(기본 `<repo>/.cache/sandbox`) 아래 `uploads/`·`output/` 이 전부다 | `settings.py:117-123`, `local_backend.py:55-58` |
| MCP 는 **두 종류**다. ① `agent_bridge_mcp` — 백엔드 프로세스에 서브앱으로 mount, **같은 포트**. ② `ontology_mcp` — 읽기 전용, **별도 프로세스**(stdio 기본, http 가능) | `host/app.py:44`, `agent_bridge_mcp/router.py:14-38`, `ontology_mcp/__main__.py:16-36` |

### 1-3. 판단

**현재 `docker-compose.yml` 의 주석 "백엔드 컨테이너 자체가 격리 경계다"는 서버 배포에서는
맞고, 데스크톱에서는 성립하지 않는다.** 세 가지 이유다.

1. **격리의 수혜자가 사라진다.** 서버에서는 여러 사용자가 한 백엔드를 공유하므로 컨테이너
   경계가 실제로 사람과 사람 사이를 가른다. 데스크톱은 1인 1머신(§3 오픈코어 경계)이고,
   그 사용자가 스스로 띄운 에이전트로부터 그 사용자의 머신을 지키는 격리다. 값이 훨씬 낮다.
2. **`cliagents` 경로가 죽는다.** 이미지에 `claude`/`codex` 가 없고, 있어도 사용자의
   `~/.claude` 로그인 세션이 컨테이너 안에 없다. 데스크톱에서 이건 단순한 기능 하나가
   아니라 **"OpenAI 키 없이 다운로드하고 바로 쓴다"** 가 가능한 유일한 경로다. 컨테이너에
   넣으면 첫 실행 화면에서 반드시 API 키를 요구하게 되고, 이는 가치 제안 1번
   ("다운로드 한 번으로 로컬 작동")과 정면으로 충돌한다.
3. **사용자가 결과물을 찾을 수 없다.** 로드맵 6~8(시각화·리포트 export)의 산출물은
   사용자가 Finder 에서 열어야 하는 파일이다. 컨테이너 볼륨 안에 있으면 `docker cp` 를
   거쳐야 꺼낼 수 있다.

반대로 **컨테이너에 넣지 않을 이유가 없는 것**들은 그대로 컨테이너다: neo4j, mindsdb,
data-fabric, neo4j-text2sql, 샘플 DB. 전부 상태를 볼륨에 두거나 무상태이고, 사용자의
파일시스템·PATH·로그인 세션에 닿을 이유가 전혀 없다.

### 결정 1 — 채택안

```
Electron main (호스트)
  ├─ ontology-studio backend   호스트 프로세스 (agent_bridge_mcp 포함, 같은 포트)
  ├─ ontology-studio MCP       호스트 프로세스 (읽기 전용, HTTP transport)
  ├─ 로컬 origin :17900        SPA 서빙 + /api 리버스 프록시
  └─ podman compose
       ├─ core         neo4j · mindsdb · data-fabric · neo4j-text2sql · antlr
       └─ sample-data  postgres · mysql   (기본 ON, 끌 수 있음)
```

- 샌드박스는 `SANDBOX_BACKEND=local`, 루트는 `<userData>/sandbox`.
- `AGENT_BACKEND` 는 사용자 설정 파일에서 고른다. 기본값은 `cliagents`로 두되,
  `claude`/`codex` 가 PATH 에 없으면 부팅 화면이 그 사실을 말하고 `deepagents` +
  API 키 입력을 안내한다. (구현: `studio.js` 가 기동 전에 `shutil.which` 와 같은 탐색을
  한 번 수행)

### 감수하는 대가 (숨기지 않는다)

`SANDBOX_BACKEND=local` 은 소스가 스스로 **"DEV-ONLY: there is no isolation between the
agent and the backend host user"** 라고 적어 둔 모드다 (`local_backend.py:10`). 데스크톱에서
이걸 채택한다는 것은, 에이전트의 bash 도구가 **사용자 권한으로 사용자 머신에서 돈다**는
뜻이다. 근거는 다음과 같다.

- `cliagents` 경로는 **이미 그렇게 돌도록 설계돼 있다** — 권한 우회 플래그와 그 이유를
  적은 주석이 소스에 있다(`cliagents_backend.py:226-229`). 즉 이 위험은 데스크톱 패키징이
  새로 도입하는 것이 아니라, 제품이 이미 선택한 것을 배포 형태에 반영하는 것이다.
- robo-architect 도 같은 판단을 했고 README 에 명시했다.
- 완화: 샌드박스 루트를 사용자 홈이 아니라 `<userData>/sandbox` 로 좁힌다.

### 채택하지 않은 안 (안 B — 백엔드도 컨테이너)

버리지는 않는다. 다음이 성립하면 다시 검토한다.

- Enterprise(서버 배포)판은 **반드시** 이쪽이다. §3 경계표가 이미 그렇게 갈라 놨다.
- OSS 데스크톱에서도 "격리 우선" 모드를 원하면, `SANDBOX_BACKEND=docker` 를 podman 에서
  쓸 수 있게 **`docker` 바이너리 이름을 설정 가능하게** 만들어야 한다(14개 호출 지점,
  §1-2 표). 이 변경 없이는 podman 환경에서 docker 샌드박스가 동작하지 않는다.
  → 별도 개선 항목으로 트래킹.

### 부수적으로 발견한 결함 — `backend/Dockerfile` 은 **현재 빌드되지 않는다**

데스크톱과 무관하게, 개발자용 `docker compose up` 경로가 이미 깨져 있다.

1. `RUN cp -r /app/backend/skills /workspace/skills` — `backend/skills/` 는 삭제됐다
   (spec 005 로 저장소 루트 `skills/` 로 이동). 실제 런타임이 읽는 경로도
   `SKILLS_ROOT = <repo>/skills` 다 (`skill_registry.py:40`).
2. `COPY backend/ ./backend/` 만 하므로 이미지에 `/app/skills` 가 없다.
3. `pyproject.toml:34` 의 `cliagents = { path = "cliagents", editable = true }` 가 요구하는
   서브모듈 디렉터리를 COPY 하지 않는다 → `uv sync --frozen` 실패.

→ 이 세 가지를 고친다. 데스크톱 결정과 무관하게 필요한 수리이고, 개발자용 compose 경로를
되살린다.

---

## 2. data-fabric 과 neo4j-text2sql 을 어떻게 담을 것인가

### 확인한 사실

| 항목 | data-fabric | neo4j-text2sql |
|---|---|---|
| Dockerfile | **있다** — `data-fabric/backend/Dockerfile` (python:3.11-slim, requirements.txt, EXPOSE 8004) | **있다** — `neo4j-text2sql/Dockerfile` (python:3.13-slim, uv, EXPOSE 8000, HEALTHCHECK `/health`) |
| 배포 이미지 | `ghcr.io/uengine-oss/robo-data-fabric:latest` 존재. **`linux/amd64` 단일** | 배포 이미지 없음 |
| 현재 실행 방식 | 호스트에서 `.venv/bin/uvicorn --port 8004` | 호스트에서 `uv run uvicorn --port 8020` |
| 호스트 의존 | 없음. Neo4j + MindsDB HTTP 만 본다 | 없음. Neo4j + MindsDB(MySQL 프로토콜) 만 본다 |

`podman manifest inspect` 로 확인한 아키텍처 (2026-08-02 실측):

```
docker.io/library/neo4j:5.26.0       → linux/amd64, linux/arm64
docker.io/mindsdb/mindsdb:v26.1.0    → linux/amd64, linux/arm64
docker.io/library/postgres:16-alpine → linux/amd64, linux/arm64 (외 5종)
docker.io/library/mysql:8.0          → linux/amd64, linux/arm64
ghcr.io/uengine-oss/robo-data-fabric:latest → linux/amd64  ← 문제
```

### 결정 2

**둘 다 컨테이너에 넣되, 이미지는 서브모듈 소스에서 패키징 시점에 로컬 빌드한다.**

- 배포된 `robo-data-fabric` 이미지는 **쓰지 않는다.** amd64 전용이므로 Apple Silicon 에서
  QEMU 로 돌게 되고, installation.md **이슈 #12** 가 같은 상황(ANTLR 파서 amd64 이미지)에서
  *"시스템 전체를 마비시킬 정도의 CPU 소모"* 를 기록했다. 전례가 있는 함정을 반복하지 않는다.
- 또한 `infra/docker-compose.robo-stack.yml:538` 의 `mysql-sample: platform: linux/amd64`
  핀도 **불필요하다** — `mysql:8.0` 은 arm64 매니페스트를 갖는다(위 실측). 데스크톱
  compose 에서는 platform 을 고정하지 않는다. (전략 문서 §4-1 "별건으로 발견된 문제" 해소)
- 로컬 빌드는 `scripts/build-images.sh` 가 수행한다:
  `podman build -t ontology-studio/data-fabric:local ../../data-fabric/backend`
  `podman build -t ontology-studio/neo4j-text2sql:local ../../neo4j-text2sql`
- 빌드 결과는 `podman save --multi-image-archive` 로 `resources/backend/core-images.tar`
  에 담아 오프라인 설치가 가능하게 한다. (git 에는 넣지 않는다 — `.gitignore`)

### 주의사항 (이식하면서 반복하지 말 것)

- **text2sql 은 부팅 시 fail-fast sanity check** 를 한다 (Neo4j 10초 / 타겟 DB 30초,
  타임아웃은 소스 하드코딩 — installation.md 이슈 #8). compose 의 `depends_on` 을
  `condition: service_healthy` 로 걸어 **neo4j·mindsdb 가 healthy 된 뒤에만** 뜨게 한다.
- **text2sql 컨테이너 내부 포트는 8000** 이다(Dockerfile). 백엔드도 8000 이지만 백엔드는
  호스트 프로세스이므로 충돌하지 않는다. 호스트 공개 포트는 동적 할당한다.
- `TEXT2SQL_BASE_URL` 은 **라우터 접두사 `/text2sql` 을 포함**하는 형태를 쓴다
  (constitution VI). env.defaults 와 compose 주입값 모두 그렇게 적는다.
- **api-gateway(9000)를 경유하지 않는다.** 30초 응답 타임아웃이 MindsDB 질의를 끊는다
  (constitution VI, 이슈 #16). 데스크톱 스택에 api-gateway 는 **넣지 않는다.**
- data-fabric 의 `MINDSDB_REPLACE_LOCALHOST` 는 사용자가 **자기 PC 의 DB** 를 등록할 때
  MindsDB 컨테이너가 호스트에 닿게 해 주는 장치다. podman 에서도 동작하도록 mindsdb 에
  `extra_hosts: host.docker.internal:host-gateway` 를 준다.

---

## 3. 팩 경계

### 전제

전략 §4-1 의 9종 표는 사업 결정이다. **아홉 개 전부 데스크톱에 들어간다.** 여기서 정하는
것은 "무엇을 뺄까"가 아니라 **"무엇이 항상 상주해야 하는가"** 다. §4-1 스스로도 남은 감량
레버 3번으로 *"온디맨드 기동 — 쓰지 않는 동안 내리는 방식"* 을 들고 있다.

### 실측 근거

| 구성요소 | idle | 사용자가 자기 DB 를 연결하면? |
|---|---|---|
| neo4j | 1.795 GiB | 필수 — 온톨로지 저장소 |
| mindsdb | 1.06 GiB | 필수 — 페더레이션 엔진 |
| **mysql-sample** | **0.488 GiB** | **불필요** — 예제 데이터일 뿐 |
| **postgres** | **0.036 GiB** | **불필요** — 예제 데이터일 뿐 |
| data-fabric | 0.100 GiB | 필수 |
| neo4j-text2sql | 0.215 GiB | 필수 |
| backend | 0.185 GiB | 필수 |
| MCP | 0.105 GiB | 필수 |

샘플 DB 2종 = **0.524 GiB**. 컨테이너 소계 3.37 GiB 의 15.6%, 전체 3.96 GiB 의 13.2%.
mysql 은 neo4j·mindsdb 다음으로 세 번째로 무거운 컨테이너다.

### 결정 3

**2단 팩 구성. `core` + `sample-data`. sample-data 는 기본 ON.**

| 팩 | 내용 | 기본 | 끌 수 있나 |
|---|---|---|---|
| `core` | neo4j · mindsdb · data-fabric · neo4j-text2sql · antlr | 항상 | 아니오 |
| `sample-data` | postgres(manufacturing) · mysql(insurance, sales) + 시드 SQL | **ON** | 예 — 메뉴 `런타임 → 예제 데이터` 체크박스 |

robo-architect 와 정반대 방향이라는 점이 중요하다. 저기서는 optional 팩이 **기본 OFF**
(설치 용량을 줄이려고)였다. 여기서는 **기본 ON** 이다 — §4-1 이 요구하는 "첫 실행에
질문하면 DB 에서 답이 나온다"가 성립해야 하기 때문이다. 끄는 것은 사용자가 자기 DB 를
연결한 **다음의** 선택이다.

- 끄면 컨테이너만 제거하고 **볼륨은 남긴다.** 다시 켤 때 시드를 다시 돌리지 않는다.
- 끄기 전에 `data-fabric` 에 등록된 데이터소스가 샘플 DB 를 가리키는지 확인해 경고한다.
  (Neo4j 의 `:DataSource` 노드는 남는데 뒤의 DB 가 사라지면 질의가 조용히 실패한다.)

### 검토했으나 채택하지 않은 것

- **MindsDB 워커 수 축소** — 전략 §4-1 이 "미확인"으로 남긴 항목. 1.06 GiB 대부분이
  멀티프로세싱 워커 4개다. 데스크톱 compose 에서 워커 수를 줄이면 가장 큰 단일 절감이
  될 수 있으나, **어떤 환경변수가 이를 제어하는지 확인하지 못했다.** 추측으로 넣지 않는다.
  별도 조사 항목.
- **neo4j 힙 추가 감량** — 이미 힙 1G/캐시 512m 로 기본 권장값 대비 4.5배 감량돼 있다
  (측정 문서 §5-1). 여기서 더 줄이는 것은 실측 없이는 안전하지 않다. 같은 값을 데스크톱
  compose 에도 그대로 쓴다.

---

## 4. `.env` 처리 — constitution VI 와 `<userData>` 의 양립

### 충돌처럼 보이는 것

- constitution VI: 환경 설정의 단일 진실 원천은 **루트 `.env`**. 서브모듈 안에 `.env` 를
  만들면 루트를 **가린다.**
- 데스크톱 관례: 사용자별 설정은 `<userData>` 에 두고 앱 업데이트가 덮어쓰지 않는다.

### 실제로는 충돌하지 않는다

두 가지 사실이 이를 푼다.

1. **설치된 앱에는 루트 `.env` 도 서브모듈도 없다.** 앱이 담는 것은 빌드 산출물(파이썬
   런타임 + 소스 사본 + SPA)이지 ontologic 체크아웃이 아니다. VI 가 막으려는 사고
   (서브모듈 `.env` 가 루트를 가림)는 설치된 앱에서 **발생할 수 없다.**
2. **`load_dotenv()` 는 `override=False` 가 기본이다** (`settings.py:13`). 즉 이미
   `os.environ` 에 있는 값은 `.env` 가 덮어쓰지 못한다. 프로세스 환경으로 주입하면
   **어떤 `.env` 가 근처에 있든 우리 값이 이긴다.**

### 결정 4

| 규칙 | 내용 |
|---|---|
| **파일은 하나** | `<userData>/ontology-studio.env` — 첫 실행에 `resources/backend/env.defaults` 에서 복사. 업데이트가 덮어쓰지 않는다 |
| **소스 트리에 쓰지 않는다** | 앱은 `ontology-studio/.env` 도, `data-fabric/.env` 도, 루트 `.env` 도 **만들지도 고치지도 않는다.** 개발 체크아웃에서 실행해도 마찬가지 — 그 경우 루트 `.env` 를 가려버리기 때문이다 (VI) |
| **주입 경로 2개** | 호스트 프로세스에는 **프로세스 환경**으로, 컨테이너에는 **compose `environment:`** 로. `env_file:` 을 쓰지 않는다 |
| **우선순위** | 사용자 셸 환경 → 설정 파일 → 앱이 정한 런타임 값(포트·크리덴셜·엔드포인트). **런타임 값이 항상 이긴다** |
| **탈출구** | `ONTOLOGY_STUDIO_ENV_FILE=<경로>` 로 기존 파일(예: ontologic 루트 `.env`)을 그대로 쓸 수 있다. 개발자가 데스크톱 셸을 체크아웃에 붙여 볼 때 쓴다 |
| **생성 크리덴셜** | Neo4j 비밀번호는 설치마다 난수 생성해 `<userData>/stack.json` 에 둔다. `NEO4J_AUTH` 는 **볼륨이 처음 만들어질 때만** 반영되므로 한 번 정하면 회전하지 않는다 |

설정 파일에 들어가는 것은 **사용자가 정해야 하는 것뿐**이다 — `AGENT_BACKEND`,
`EXTERNAL_AGENT_ID`, `OPENAI_API_KEY`/`OPENAI_BASE_URL`, 모델 이름, `LLM_PROVIDER`(text2sql),
`MCP_ALLOW_DATASOURCE_EXPANSION`. Neo4j URI·포트·서비스 URL 은 **넣지 않는다.** 앱이 정하고
앱이 주입한다. (넣어 두면 사용자가 고쳤을 때 조용히 무시되어 더 나쁘다.)

---

## 5. 포트

### 왜 고정 포트를 쓰면 안 되는가 — 기록된 사고들

installation.md 가 남긴 것은 가정이 아니라 **이 머신에서 실제로 일어난 일**이다.

| 근거 | 내용 |
|---|---|
| 이슈 #1 | 다른 프로젝트(process-gpt)가 **5432 · 7474 · 7687 · 8000 · 8010** 을 점유. postgres→5433, neo4j→7475/7688, text2sql→8020 으로 전부 재매핑해야 했다 |
| 이슈 #1 주석 | *"docker 포트포워딩은 프로세스명이 `com.docke` 로만 보여서 놓치기 쉽다"* — 사람이 눈으로 찾는 방식은 실패한다 |
| 이슈 #11 | api-gateway 의 text2sql 라우트가 `http://127.0.0.1:8000` **하드코딩**이라 8020 환경에서 라우팅이 깨졌다 |
| 이슈 #2 | 이전 설치의 잔재 컨테이너가 같은 이름으로 남아 기동 실패 |
| 이 머신 현재 상태 | podman 머신 `robo-architect` 가 **지금도 돌고 있다.** 다른 제품의 데스크톱 앱이 같은 사용자 PC 에 공존하는 것은 예외가 아니라 전제다 |

데스크톱 앱은 개발자 머신이 아니라 **아무 상태나 될 수 있는 사용자 PC** 에서 뜬다.
고정 포트는 "설치 한 번으로 로컬에서 끝난다"는 가치 제안을 첫 실행에서 깨뜨린다.

### 결정 5

**호스트에 공개하는 포트는 전부 동적 할당한다.** 선호 포트가 비어 있으면 그것을 쓰고,
아니면 임시 포트를 잡는다. 참고 구현의 `ports.js` 를 그대로 가져오되 아래를 유지한다.

- **bind 검사만으로 부족하다.** 다른 프로세스가 `0.0.0.0:8000` 을 잡고 있어도
  `127.0.0.1:8000` bind 는 성공할 수 있고, 그러면 우리 프록시가 남의 백엔드에 요청을
  넘긴다. robo-architect 가 실제로 겪은 사고다 — bind 가능 **그리고** 연결 시 무응답
  둘 다 확인한다.
- 컨테이너 간 통신은 **compose 네트워크의 서비스 이름**을 쓴다(`neo4j:7687`,
  `mindsdb:47334`). 호스트 포트를 경유하지 않으므로 동적 할당의 영향을 받지 않는다.
- MindsDB 의 47334/47335 는 **호스트에 공개하지 않는다.** data-fabric·text2sql 이
  네트워크 내부에서만 쓴다. 공개 표면을 줄이는 것이 곧 충돌 표면을 줄이는 것이다.

| 용도 | 선호 | 공개 | 비고 |
|---|---|---|---|
| 앱 origin (SPA + `/api` 프록시) | 17900 | 127.0.0.1 | 창이 여는 주소 |
| backend (uvicorn, agent_bridge_mcp 포함) | 8000 | 127.0.0.1 | 호스트 프로세스 |
| **MCP (읽기 전용, HTTP)** | **8100** | 127.0.0.1 | **sticky — 아래 참조** |
| neo4j HTTP / Bolt | 17474 / 17687 | 127.0.0.1 | 호스트 backend 가 Bolt 로 붙는다 |
| data-fabric | 18004 | 127.0.0.1 | 호스트 backend 가 붙는다 |
| neo4j-text2sql | 18020 | 127.0.0.1 | 호스트 backend 가 붙는다 |
| ANTLR 코드 파서 | 18081 | 127.0.0.1 | 게이트웨이 심이 `/api/gateway/antlr/**` 를 보낸다 |
| mindsdb | — | 공개 안 함 | 네트워크 내부 전용 |
| postgres / mysql (sample) | — | 공개 안 함 | MindsDB 가 서비스 이름으로 붙는다 |

### 예외 — MCP 포트는 sticky 다

`ontology_mcp` 는 **외부 AI 클라이언트(Cursor, Claude Desktop 등)가 손으로 설정 파일에
적는 주소**다. 이것이 제품의 핵심 차별점이고(전략 §1), 실행할 때마다 포트가 바뀌면
사용자가 매번 설정을 고쳐야 한다.

→ 첫 실행에 할당한 포트를 `<userData>/stack.json` 에 저장하고 **이후 실행에서 재사용**한다.
그 포트가 점유돼 있으면 새로 잡고 저장값을 갱신하되, 부팅 화면과 메뉴에 **복사 가능한
MCP URL** 을 항상 표시한다. 동적 할당의 견고함과 실사용상의 안정성을 둘 다 얻는다.

### 프론트엔드 origin 문제 (구현에서 걸리는 지점)

`frontend/src/shared/hooks/useOntologyStudio.js:3` 이
`import.meta.env.VITE_API_BASE || 'http://localhost:8000'` 로 **절대 URL** 을 만들고,
51곳에서 `${API}/api/...` 를 조립한다. 데스크톱은 origin 포트가 런타임에 정해지므로 빌드
시점에 이 값을 박을 수 없다.

→ 같은 origin 을 쓰도록 `??` 로 바꾸고(빈 문자열이 유효한 값이 되도록), `new URL(...)`
4곳에 `window.location.origin` 을 base 로 넘긴다. 컨테이너 배포는 `VITE_API_BASE` 를
그대로 주므로 **동작이 바뀌지 않는다.**

---

## 6. 검증에 대한 정직한 경계

전략 §6 이 요구하는 **영상 증거**는 이 작업에서 자동 생성할 수 없다. 이 개발 세션의
셸은 **macOS GUI 앱을 띄우지 못한다**(`open` 이 exit 0 을 반환하나 프로세스가 남지 않음).
따라서:

- **자동 검증 가능**: compose 파일 문법, 이미지 태그/아키텍처 유효성, Node 스크립트 문법,
  SPA 빌드, 파이썬 런타임 번들.
- **사람이 해야 함**: 앱 창이 실제로 뜨는가, 부팅 순서가 끝까지 가는가, 첫 질의가
  답을 내는가, 그리고 그 화면 녹화.

절차서는 `ontology-studio/desktop/README.md` 의 **"직접 확인하는 법"** 절에 있다.

---

## 7. 아직 결정되지 않은 것

- **코드사이닝** — ad-hoc 서명만으로는 빌드한 머신에서만 돈다. 배포에는 Apple Developer ID
  + notarization 이 필요하다(전략 §7 과 동일한 미결 사항).
- **MindsDB 워커 수** — 가장 큰 남은 감량 레버인데 제어 변수를 확인하지 못했다(§3).
- **Podman VM 메모리 상한** — robo-architect 머신은 6144MB 로 설정돼 있다. ontology-studio
  전용 머신을 만들 때 얼마로 잡을지는 실측이 필요하다. 잠정 6144MB(실측 idle 3.96 GiB +
  여유), 사용자가 `ONTOLOGY_STUDIO_PODMAN_MEMORY` 로 바꿀 수 있게 한다.
- **`SANDBOX_BACKEND=docker` 의 podman 지원** — 컨테이너 격리 모드를 데스크톱에서도 쓰려면
  `docker` 바이너리 이름을 설정 가능하게 만들어야 한다(14개 호출 지점, §1-3).

---

## 추가 결정 (2026-08-03) — ANTLR 코드 파서를 core 팩에 넣는다

**결정**: `antlr-code-parser` 를 **core 팩**에 넣는다. 이미지는 §2 의 data-fabric 과
**같은 규칙**으로 서브모듈 소스에서 로컬 빌드한다.

**왜 core 인가 (optional 팩이 아니라)**: 「메타데이터 증강」 화면은 이미 데스크톱에서
경로 모드로 뜨고 있었다(frontend-integration §10). 그 화면의 「분석 시작」이 눌리는데
아무 일도 일어나지 않는 상태를 남겨 두는 것이, 팩을 하나 늘리는 것보다 나쁘다.

**왜 배포 이미지를 쓰지 않는가**: `ghcr.io/uengine-oss/robo-antlr-parser:latest` 는
`linux/amd64` **전용**이다(`podman manifest inspect` 실측). §2 의 data-fabric 과 같은
상황이고, `installation.md` 이슈 #12 가 같은 조건에서 *"시스템 전체를 마비시킬 정도의
CPU 소모"* 를 기록했다.

**대가**: 코어 팩 유휴가 **약 344 MB** 늘어난다(파싱을 한 번 하면 ~394 MB). 서브모듈
Dockerfile 의 기본 힙(`-Xms512m -Xmx4096m`)을 그대로 뒀다면 472 MiB 였다 — compose 에서
`entrypoint` 를 교체해 `-Xms128m -Xmx1536m` 으로 낮췄다. 측정과 근거는
`memory-footprint-measurement.md` §9.

**미해결로 남긴 것**: 파싱 다음 단계인 robo-analyzer(5502)·robo-data-catalog(5503)은
여전히 팩에 없다. 즉 코드 분석 파이프라인은 **1단계까지만** 동작한다. 이 둘을 넣을지는
별도 결정이다 — 넣으면 코어 팩이 다시 크게 늘고, 그 서비스들은 LLM 키를 요구한다.

---

## 추가 결정 (2026-08-03) — robo-analyzer·robo-data-catalog 는 **호스트 프로세스**로 넣는다

바로 위 항목이 "미해결로 남긴 것" 이라고 적은 그 둘이다. 결론부터: **넣는다. 단
컨테이너가 아니라 호스트 프로세스로.**

### 왜 넣는가

「분석 시작」이 눌리는데 `❌ 분석 중 문제가 생겼어요: ROBO 백엔드 서비스가 동작하지
않습니다` 로 끝나는 상태를 남겨 두는 것은, 위 항목이 파서를 core 에 넣은 것과 **같은
이유로** 받아들일 수 없다. 화면이 있는데 눌러도 안 되는 것이 팩이 무거운 것보다 나쁘다.

### 왜 컨테이너가 아닌가 — 세 근거가 각각 독립적으로 성립한다

1. **파서와 파일시스템으로 이어져 있다.** 분석기는 소스를 재파싱하지 않고 ANTLR 가
   떨군 `analysis/*.json` 만 읽는다(`analysis_flow/step2_load_ast/load_ast_step.py:3`).
   즉 둘 사이는 HTTP 계약이 아니라 **디렉터리 공유**다. 그래서 이 스택에
   **바인드 마운트가 정확히 하나** 생긴다 — `<userData>/robo-data` → 파서의 `/app/data`.

   compose.yml 머리말이 바인드 마운트를 금지한 이유는 *"앱 리소스는 `/Applications`
   아래라 podman machine 의 공유 범위($HOME) 밖"* 이었다. `<userData>` 는
   `~/Library/Application Support/...` 로 **그 범위 안**이다. 2026-08-03 실측으로
   양방향 읽기·쓰기를 확인했다(컨테이너가 uid 7474 로 쓴 파일이 호스트에서 보인다).

   이미 마운트가 하나 필요하다면, 그 위에서 분석기까지 컨테이너에 넣어 얻는 것이 없다.
2. **`/robo/source` 는 사용자 디스크의 원본을 절대경로로 읽는다.** api-gateway 주석이
   *"분석기만 소스 디스크 접근"* 이라고 적어 둔 그것이고, 코드뷰가 그 위에 그려진다.
   경로 모드에서 사용자가 고른 임의 폴더는 컨테이너가 볼 수 없다. §1 의 판정 기준
   ("컨테이너 경계를 넘으면 제품이 무엇인지가 바뀌는 부분만 호스트") 에 정확히 걸린다.
3. **두 서브모듈에 Dockerfile 이 없다.** 만들려면 서브모듈을 고쳐야 하는데
   (이 작업의 규칙상 최후 수단), 분석기는 `sentence-transformers`(torch) 를 끌고 와
   `.venv` 만 **932MB** 다. 이미지로 구우면 수 GB 짜리 팩이 하나 더 생긴다.

부수 효과 하나 더: 호스트 프로세스는 **podman machine 6144MB 상한 밖**이다. §9-3 이
기록한 "VM 고갈 → 엉뚱한 컨테이너 OOMKill" 위험대에 가까워지지 않는다.

### 대가 (숨기지 않는다)

- **패키징에 파이썬 런타임이 두 벌 더 들어간다.** `build-runtime.sh --with-robo` 로
  **기본 OFF** 다 — 코드 분석이 필요 없는 배포까지 1GB 를 지고 갈 이유가 없다. 켜지
  않으면 앱은 정상 기동하고 코드 분석만 비활성으로 안내된다.
- **유휴 메모리가 약 535 MB 늘어난다** (분석기 421 + 카탈로그 115). core 소계 대비
  +22%. 분석기 몫의 대부분은 torch 임포트이고 **분석을 돌리기 전부터** 그렇다.
  측정과 근거: `memory-footprint-measurement.md` §10.
- **락 파일이 없다.** 두 서브모듈에는 `pyproject.toml`/lock 이 없고 `requirements.txt`
  만 있다. studio 런타임(`uv export --locked`)보다 재현성이 낮다 — 두 requirements 가
  패치 버전까지 고정돼 있는 것이 유일한 방어선이다.

### 이 결정으로 해결되지 **않은** 것

`robo-data-frontend` 와 `robo-data-analyzer` 의 `/robo/analyze` 계약이 실제로
어긋나 있다 — 프론트가 `project_name` 을 보내지 않는데 분석기는 필수로 받는다(422).
**이건 데스크톱 고유 문제가 아니라 Spring 게이트웨이를 거치는 서버 배포에서도 똑같이
깨진다.** 지금은 데스크톱 셸이 본문을 번역해 우회하고 있고(`webserver.js
translateAnalyzeBody`), 어느 저장소를 고칠지는 그 저장소 주인이 정할 일이다.
자세한 내용과 실측: `evidence/11-analysis-pipeline/README.md` §6.

또한 **LLM 단계(3단계 이후)는 검증하지 못했다.** 이 머신의 OpenAI 키가 두 개 다
만료돼 있다(실측 401). 파싱 → AST 적재 → Neo4j → 그래프 되읽기까지는 실측했다.
