# 🤖 LangChain Agent & Tool Integration
### **커스텀 Tool · 웹 스크래핑 · SQL Toolkit** — LLM이 외부 시스템(웹·DB·OS)에 직접 접근하도록 만들어 본 LangChain Agent 통합 파이프라인

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-412991?style=for-the-badge&logo=openai&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)
![BeautifulSoup](https://img.shields.io/badge/BeautifulSoup-43B02A?style=for-the-badge&logo=python&logoColor=white)
![Matplotlib](https://img.shields.io/badge/Matplotlib-11557C?style=for-the-badge&logo=python&logoColor=white)

---

## 📌 프로젝트 요약 (Project Overview)

LLM은 그 자체로는 학습이 끝난 시점 이후의 정보, 즉 지금 이 순간의 환율이나 우리 회사 DB 안의 직원 명단 같은 것은 절대 알지 못합니다. 처음 LangChain을 공부하면서 가장 인상 깊었던 점은, 이런 한계를 "더 똑똑한 모델"로 푸는 것이 아니라 LLM에게 직접 호출할 수 있는 **도구(Tool)** 를 쥐여 주는 방식으로 푼다는 것이었습니다.

이 프로젝트는 그 발상을 직접 만져 보기 위해, 가상의 중견 전자부품 기업 "모든전자(Modeun Electronics)"의 사내 보조 챗봇이라는 시나리오를 잡고 LangChain Agent에 세 종류의 외부 연동 Tool을 붙여 본 기록입니다. 첫째로 7개 해외 거점의 현재 시각을 한꺼번에 알려 주는 멀티 도시 시간 Tool, 둘째로 네이버 증권 페이지를 실시간으로 긁어 USD/KRW 환율을 가져오는 웹 스크래핑 Tool, 셋째로 사내 SQLite DB에서 직원 정보를 자연어로 조회하지만 변경 쿼리는 절대 실행하지 않는 읽기 전용 SQL Agent 입니다. 단순히 함수를 만드는 데서 끝내지 않고, **LLM이 어떤 도구를 언제 호출하는지 / 어떤 안전장치를 걸어야 의도하지 않은 작업을 막을 수 있는지** 까지 체득하는 것을 목표로 했습니다.

---

## 🎯 핵심 목표 (Motivation)

| 핵심 역량 | 상세 목표 및 엔지니어링 포인트 |
| :--- | :--- |
| **Tool 설계 (Custom Tool Design)** | `@tool` 데코레이터, 타입 힌트, docstring을 정확히 작성하여 LLM이 호출 시점·인자 의미를 스스로 판단하도록 가이드 |
| **외부 데이터 연동 (External I/O)** | `requests` + `BeautifulSoup4` 로 실시간 웹 스크래핑, `zoneinfo` 로 시간대 변환, SQLite로 사내 DB 모사 |
| **Toolkit 활용 (Built-in Toolkit)** | `SQLDatabaseToolkit` 의 4개 툴(`list_tables` / `schema` / `query_checker` / `query`)을 묶어 자연어 → SQL 자동 변환 |
| **안전한 Agent 설계 (Safety Boundary)** | System Prompt와 dialect/top_k 주입으로 **READ-ONLY** 정책을 강제하여, 사용자가 삭제/수정을 요청해도 거절하도록 설계 |

---

## 📂 프로젝트 구조 (Project Structure)

```text
22. langchain-agent-tool-integration/
├─ data/
│  └─ modeun.db                              # SQLite 더미 DB (실행 시 자동 생성, gitignore 대상)
├─ results/
│  ├─ fig_01_global_office_clock.png         # 7개 해외 거점 현재 시각 시각화
│  ├─ fig_02_employee_distribution.png       # 국가별 직원 분포 + 경력 연수 막대 그래프
│  ├─ fig_03_pipeline_overview.png           # Agent ↔ Tool 호출 흐름 다이어그램
│  └─ agent_run_log.json                     # Agent 실행 로그 (질문·답변·사용 툴)
├─ src/
│  └─ agent_tool_pipeline.py                 # 통합 실행 스크립트 (mode 인자로 단계별 실행)
├─ .env.example                              # API_KEY · BASE_URL 환경변수 예시
├─ .gitignore
├─ README.md
└─ requirements.txt
```

> **Note**: `.env` 파일에 LLM 프록시 서버의 `API_KEY` 와 `BASE_URL` 을 채워 넣어야 LLM 호출 모드가 동작합니다.

---

## ⚙️ requirements.txt

```text
langchain-community==0.4.1
langchain-openai==1.1.16
langchain-core>=1.0.1
beautifulsoup4==4.14.3
requests>=2.32.5
SQLAlchemy>=2.0.0
python-dotenv>=1.0.0
matplotlib>=3.8.0
tzdata>=2024.1
```

---

## 🏗️ Architecture

### 1. Agent ↔ Tool 호출 흐름

| LangChain Agent ↔ Tool 호출 흐름 (도식) |
| :---: |
| ![pipeline](results/fig_03_pipeline_overview.png) |

LLM 단독으로는 답할 수 없는 질문이 들어오면, Agent는 등록된 Tool 중에서 docstring과 시그니처를 보고 적절한 도구를 선택해 호출합니다. 결과를 받은 뒤 다시 자연어로 정리해서 사용자에게 답변하는 구조입니다.

### 2. Tool별 동작 원리

| 분류 | Tool 이름 | 입력 | 동작 방식 |
| :---: | :--- | :---: | :--- |
| 시간 조회 | `get_global_office_times` | 없음 | `zoneinfo` 로 7개 도시 현재 시각을 동시에 계산 후 포매팅 |
| 환율 스크래핑 | `get_usd_krw_exchange_rate` | 없음 | 네이버 증권 페이지 → `BeautifulSoup` CSS 셀렉터 → `<span class="value">` 추출 |
| SQL 조회 | `sql_db_list_tables` | 없음 | DB 안에 어떤 테이블이 존재하는지 목록 반환 |
| SQL 조회 | `sql_db_schema` | 테이블명 | 컬럼 정의 + 샘플 3행을 LLM에게 노출 |
| SQL 조회 | `sql_db_query_checker` | SQL 쿼리 | 실행 전 문법·로직 검증 (1차 안전장치) |
| SQL 조회 | `sql_db_query` | SQL 쿼리 | 실제 쿼리 실행 후 결과 반환 |

### 3. 안전한 SQL Agent 설계 — System Prompt 주입

```text
다음 규칙을 반드시 준수한다.
- SQL 문법은 sqlite 를 따른다.
- 결과는 최대 5건으로 제한한다.
- INSERT, UPDATE, DELETE, DROP, CREATE 등 변경 구문은 실행하지 않는다.
- 변경 요청이 들어오면 SQL Tool을 실행하지 않고, 정중히 거절한다.
- 항상 sql_db_list_tables 로 테이블을 먼저 확인한 뒤 sql_db_schema 를 호출한다.
```

`db.dialect` 값을 시스템 프롬프트에 직접 주입함으로써, 동일 코드를 MySQL이나 PostgreSQL로 옮겼을 때도 LLM이 올바른 방언으로 쿼리를 생성하도록 했습니다. 또한 `top_k=5` 제한을 두어 거대한 결과셋을 한꺼번에 토해내 토큰을 폭발시키는 상황도 방지했습니다.

---

## 🔍 핵심 구현 상세 (Implementation Details)

### 1. Custom Tool — `@tool` 데코레이터

```python
@tool
def get_global_office_times() -> str:
    """
    모든전자의 7개 해외/국내 거점 현재 시각을 한꺼번에 반환합니다.
    해외 영업/물류 협업 시 도시별 현지 시각이 필요할 때 사용합니다.
    """
    weekday_kr = ["월", "화", "수", "목", "금", "토", "일"]
    rows: list[str] = []
    for label, tz_name in GLOBAL_OFFICES.items():
        now = datetime.now(ZoneInfo(tz_name))
        wd = weekday_kr[now.weekday()]
        rows.append(f"- {label}: ... ({wd}) ...")
    return "\n".join(rows)
```

> docstring과 타입 힌트가 단순 주석이 아니라, LLM이 "이 함수를 언제 어떻게 부르면 되는지" 판단하는 **실제 입력**입니다. 이걸 모르고 첫 시도에서 docstring을 비워 두자, Agent가 시간 질문에도 툴을 호출하지 않는 경험을 했습니다.

### 2. 웹 스크래핑 Tool

```python
@tool
def get_usd_krw_exchange_rate() -> str:
    """네이버 증권에서 실시간 USD/KRW 환율을 스크래핑하여 반환합니다."""
    response = requests.get("https://finance.naver.com/marketindex/", timeout=5)
    soup = BeautifulSoup(response.text, "html.parser")
    target = soup.select_one("#exchangeList > li.on > a.head.usd > div > span.value")
    return target.get_text(strip=True) if target else "환율 정보를 찾을 수 없음"
```

### 3. SQLDatabaseToolkit — 자연어 → SQL

```python
db = SQLDatabase.from_uri(f"sqlite:///{DB_PATH}")
toolkit = SQLDatabaseToolkit(db=db, llm=llm)
sql_tools = toolkit.get_tools()  # 4개 툴 자동 생성

agent = create_agent(model=llm, tools=sql_tools, system_prompt=READONLY_PROMPT)
```

### 4. 실행 모드 (`agent_tool_pipeline.py`)

```bash
# 1. 의존성 설치 후 .env 작성
pip install -r requirements.txt

# 2. 단계별 실행
python src/agent_tool_pipeline.py --mode times       # 멀티 도시 시간 Agent
python src/agent_tool_pipeline.py --mode exchange    # 환율 스크래핑 Agent
python src/agent_tool_pipeline.py --mode sql         # READ-ONLY SQL Agent
python src/agent_tool_pipeline.py --mode visualize   # 시각화만 생성
python src/agent_tool_pipeline.py --mode all         # 전체 파이프라인 일괄 실행
```

---

## 📊 시각화 결과 (Results)

### 1. 글로벌 거점 현재 시각 스냅샷

![global clock](results/fig_01_global_office_clock.png)

| 항목 | 내용 |
| :--- | :--- |
| **구성** | 7개 도시(서울·베이징·호치민·방콕·바르샤바·프랑크푸르트·LA) 현재 시각을 가로 막대 + 텍스트 라벨로 표기 |
| **확인 포인트** | 색상은 시간대를 반영하여, 새벽(보라색)·오전(파랑)·오후(초록)으로 자연스럽게 그라데이션됨 |
| **인사이트** | `get_global_office_times` Tool 한 번의 호출로 동시에 계산되는 7개 도시 데이터를 그대로 시각화 — Agent가 받는 출력이 그래프와 1:1로 대응 |

### 2. SQL Agent 조회 결과 — 인사 데이터

![employee distribution](results/fig_02_employee_distribution.png)

| 항목 | 내용 |
| :--- | :--- |
| **구성** | 좌: 국가코드별 직원 분포(파이 차트, KR 60% / 그 외 4개국 각 10%), 우: 직원 10명의 경력 연수 (가로 막대) |
| **확인 포인트** | 최영미 부장(27년) → 김민철 차장(15년) 순으로 베테랑 분포가 확인됨 |
| **인사이트** | 자연어 질의 "가장 먼저 입사한 사람"의 정답(최영미 부장, 1998-05-20)이 그래프 최상단과 일치함을 시각적으로 검증 |

### 3. Agent ↔ Tool 호출 흐름

![pipeline](results/fig_03_pipeline_overview.png)

| 항목 | 내용 |
| :--- | :--- |
| **구성** | 사용자 질문 → Agent → 등록된 Tool 그룹(시간 / 환율 / SQL Toolkit 4종) → 최종 답변 |
| **확인 포인트** | LLM 자체는 단 1개의 Agent로 유지되고, Tool만 추가 등록하면 능력이 확장되는 LangChain의 핵심 설계 |

---

## ✨ 주요 결과 및 분석 (Key Findings & Analysis)

### 1. docstring이 곧 LLM의 가이드라인

처음에는 협업용 주석 정도로만 생각하고 docstring을 비워 둔 채 Tool을 등록했더니, LLM이 시간 관련 질문이 들어와도 툴을 부르지 않고 "실시간 시간을 알 수 없다"는 식의 일반 답변만 했습니다. docstring에 "사용자가 시간을 묻는 경우 사용한다" 한 문장을 추가하자 그 즉시 정확하게 호출하기 시작했습니다. **LLM은 함수의 코드를 읽지 않습니다 — docstring과 시그니처만 봅니다.**

### 2. SQLDatabaseToolkit이 자동으로 만들어 주는 4개 툴의 시너지

`sql_db_query` 하나만 있어도 동작하긴 하지만, `sql_db_list_tables → sql_db_schema → sql_db_query_checker → sql_db_query` 순서로 4단계를 거치게 하면 LLM이 **DB 구조를 모르는 상태에서도** 안전하게 답을 만들어 냅니다. 이것은 마치 신입 개발자가 DBA 가이드 없이 DB를 처음 보고도 일을 시작할 수 있게 만드는 발판과 비슷했습니다.

### 3. 시스템 프롬프트는 SQL 인젝션 방어선이 될 수 있다

"레 티 흐엉 사원을 삭제해줘" 같은 변경 요청이 들어왔을 때, 단순히 권한을 막는 대신 시스템 프롬프트에서 "변경 구문은 실행하지 않는다"고 못 박는 것만으로 LLM이 SQL Tool을 아예 호출하지 않고 거절했습니다. 즉, **프롬프트 자체가 정책 레이어**가 될 수 있다는 것이 흥미로웠습니다(다만 이것은 1차 방어선일 뿐, 운영 환경에서는 DB 사용자 권한 자체를 SELECT-only로 분리하는 것이 정석입니다).

---

## 💡 회고록 (Retrospective)

이 프로젝트를 시작하기 전까지 저에게 LLM이란 그저 "똑똑하게 말하는 박스"에 불과했습니다. 질문을 던지면 그럴듯한 답이 나오긴 하지만, 정작 "지금 환율이 얼마야?", "우리 회사 직원 중에 가장 오래된 사람이 누구야?" 같은 현실적인 질문 앞에서는 한 발도 나아가지 못하는 한계가 분명했습니다. LangChain의 Tool 개념을 처음 배웠을 때, 이 한계를 "더 큰 모델"이 아니라 "외부 도구"로 풀어낸다는 발상이 무척 신선했습니다. 모델을 키우는 게 아니라, 모델에게 손과 발을 달아 주는 접근이었기 때문입니다.

처음 Tool을 직접 만들면서 가장 당황스러웠던 부분은 docstring이었습니다. 평소에는 코드 가독성을 위해 짧게 쓰던 주석을, LangChain에서는 LLM이 "이 함수를 언제 써야 하는지" 판단하는 실제 입력값으로 취급한다는 점을 처음 알게 되었습니다. 멀티 도시 시간 Tool에 docstring을 비워 두었을 때 LLM이 시간 질문에도 도구를 부르지 않던 경험은, 그동안 제가 주석을 사람만 읽는 것이라 여겨 왔다는 사실을 자각하게 만들었습니다. 이후로는 함수 이름·매개변수 타입·docstring을 한 묶음의 "LLM용 사용 설명서"로 다시 보기 시작했습니다.

웹 스크래핑 Tool을 만들 때도 비슷한 깨달음이 있었습니다. 네이버 증권 페이지의 환율 영역은 페이지 개편이 있을 때마다 CSS 셀렉터 위치가 살짝씩 바뀌는데, 이런 외부 의존성은 결국 Tool의 안정성과 직결됩니다. LLM이 똑똑해도 Tool이 깨지면 챗봇 전체가 멈춘다는 것을 보면서, AI 시스템에서도 결국 평범한 백엔드 엔지니어링 기본기 — 타임아웃, 예외 처리, 명확한 실패 메시지 — 가 그대로 중요하다는 점을 다시 느꼈습니다. 그래서 환율 Tool에는 `try/except`로 실패를 잡고 사람이 읽기 좋은 메시지로 돌려주도록 만들었고, 이 작은 처리 하나가 Agent의 답변 품질을 눈에 띄게 안정적으로 만들어 주었습니다.

가장 인상 깊었던 부분은 SQL Agent를 만들면서 "시스템 프롬프트가 곧 정책"이 될 수 있다는 점을 직접 본 순간이었습니다. "박지수 대리를 DB에서 삭제해줘" 같은 위험한 요청이 들어왔을 때, 별도의 차단 로직 없이도 시스템 프롬프트에 "변경 구문은 실행하지 않고 정중히 거절한다"라는 규칙 한 줄을 적어 두었더니, LLM이 정말로 SQL Tool을 부르지 않고 정중하게 거절하는 답을 내놓았습니다. 물론 이게 완벽한 방어선이라고 생각하지는 않습니다. 결국 운영 환경에서는 DB 사용자 권한 자체를 SELECT-only로 분리하는 식의 인프라 차원 안전장치가 정석이겠지만, 그 앞에 "프롬프트 차원 1차 방어선"을 둘 수 있다는 것을 직접 확인한 경험은 컸습니다.

또 한 가지 의외였던 부분은, `SQLDatabaseToolkit` 이 자동으로 만들어 주는 네 개의 툴(`list_tables`, `schema`, `query_checker`, `query`)이 마치 한 사람의 사고 흐름처럼 자연스럽게 이어진다는 점이었습니다. LLM은 DB 구조를 전혀 모르는 상태에서 시작하지만, 먼저 어떤 테이블이 있는지 묻고, 다음으로 그 테이블의 컬럼을 보고, 그 다음 쿼리를 만들어 검증한 뒤, 마지막에 실행하는 순서로 답을 만들어 갑니다. 사람이 처음 보는 데이터베이스에 접근할 때 거치는 절차와 거의 똑같았습니다. 단순히 함수 네 개를 묶어 놓은 것이 아니라, "안전하게 DB를 처음 만나는 절차" 자체를 추상화해 둔 설계라는 점이 인상 깊었습니다.

이번 프로젝트를 통해 LLM은 외부 시스템과 연결될 때 비로소 진짜 "도구"가 된다는 것을 직접 경험했습니다. 더불어 그 연결을 만드는 일에서, 화려한 AI 기술보다는 평범한 엔지니어링 기본기 — 타입 힌트, docstring, 예외 처리, 권한 분리, 로깅 — 가 더 큰 무게를 가진다는 것도 깨달았습니다. 다음 단계에서는 단일 Agent에 도구를 더 붙이는 방향이 아니라, 여러 Agent가 서로 협력하는 멀티 에이전트 구조나, 사내 문서까지 검색해 답할 수 있는 RAG 기반 챗봇으로 시야를 확장해 보고 싶습니다. 이번에 손에 익힌 Tool 설계 감각이, 앞으로 더 복잡한 시스템을 만들 때도 단단한 기반이 되어 줄 것이라고 믿습니다.

---

## 🔗 참고 자료 (References)

- LangChain Documentation — `create_agent` / `@tool` Decorator (LangChain AI, 2024)
- LangChain Community — `SQLDatabaseToolkit` API Reference
- BeautifulSoup4 — HTML Parser for Python (Crummy, 2024)
- Naver Finance Market Index Page — Real-time Exchange Rate (`finance.naver.com/marketindex`)
- NVIDIA AI ACADEMY · 챗봇 프로젝트 — `chapter_02_agent_tool` / `chapter_03_sql_agent`
