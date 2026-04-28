"""
LangChain AI Agent & Tool Integration Pipeline
================================================
Custom Tool 기반 멀티 도시 시간 조회 + 환율 스크래핑 + SQLite 자연어 조회
파이프라인을 통합한 단일 실행 스크립트입니다.

실행 모드:
    --mode times        : 멀티 도시 시간 조회 Agent 데모
    --mode exchange     : 네이버 증권 환율 스크래핑 Tool 데모
    --mode sql          : SQLDatabaseToolkit 기반 SQL Agent 데모 (READ-ONLY)
    --mode visualize    : 실행 결과 시각화 (PNG 저장)
    --mode all          : 위 단계 전체 순차 실행

원본 노트북:
    chapter_02_agent_tool.ipynb / chapter_03_sql_agent.ipynb
"""

import argparse
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI

ROOT_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT_DIR / "results"
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "modeun.db"

RESULTS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

# 한글 폰트 설정 (Windows: Malgun Gothic)
plt.rcParams["font.family"] = ["Malgun Gothic", "AppleGothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


# ────────────────────────────────────────────────────────────────────────────
# 1. LLM 초기화 (프록시 서버 호환)
# ────────────────────────────────────────────────────────────────────────────
def build_llm() -> ChatOpenAI:
    load_dotenv()
    return ChatOpenAI(
        base_url=os.getenv("BASE_URL"),
        api_key=os.getenv("API_KEY"),
        model="ignored-by-proxy",
    )


# ────────────────────────────────────────────────────────────────────────────
# 2. Tool 정의 — 멀티 도시 시간 (해외 거점 다수 보유한 모든전자 시나리오)
# ────────────────────────────────────────────────────────────────────────────
GLOBAL_OFFICES: dict[str, str] = {
    "서울 (대한민국)": "Asia/Seoul",
    "베이징 (중국)": "Asia/Shanghai",
    "호치민 (베트남)": "Asia/Ho_Chi_Minh",
    "방콕 (태국)": "Asia/Bangkok",
    "바르샤바 (폴란드)": "Europe/Warsaw",
    "프랑크푸르트 (독일)": "Europe/Berlin",
    "로스앤젤레스 (미국)": "America/Los_Angeles",
}


@tool
def get_global_office_times() -> str:
    """
    모든전자(Modeun Electronics)의 7개 해외/국내 거점 현재 시각을 한꺼번에 반환합니다.
    해외 영업/물류 협업 시 도시별 현지 시각이 필요할 때 사용합니다.
    매개변수는 필요하지 않습니다.

    Returns:
        str: 도시별 현지 시각이 줄바꿈으로 구분된 문자열
    """
    weekday_kr = ["월", "화", "수", "목", "금", "토", "일"]
    rows: list[str] = []
    for label, tz_name in GLOBAL_OFFICES.items():
        now = datetime.now(ZoneInfo(tz_name))
        wd = weekday_kr[now.weekday()]
        rows.append(
            f"- {label}: {now.strftime('%Y년 %m월 %d일')} ({wd}) "
            f"{now.strftime('%H:%M:%S')} (UTC{now.strftime('%z')})"
        )
    return "\n".join(rows)


@tool
def get_usd_krw_exchange_rate() -> str:
    """
    네이버 증권에서 실시간 USD/KRW 환율을 스크래핑하여 반환합니다.
    해외 거래처 견적 작성 시 환산 기준 환율 확인에 사용합니다.
    매개변수는 필요하지 않습니다.

    Returns:
        str: '1,XXX.XX' 형태의 환율 문자열. 실패 시 오류 메시지.
    """
    try:
        page_url = "https://finance.naver.com/marketindex/"
        response = requests.get(page_url, timeout=5)
        soup = BeautifulSoup(response.text, "html.parser")
        target = soup.select_one(
            "#exchangeList > li.on > a.head.usd > div > span.value"
        )
        return target.get_text(strip=True) if target else "환율 정보를 찾을 수 없음"
    except Exception as exc:  # 네트워크 단절/사이트 점검 대비
        return f"환율 조회 실패: {exc}"


# ────────────────────────────────────────────────────────────────────────────
# 3. SQLite 더미 DB — 모든전자 직원 10명
# ────────────────────────────────────────────────────────────────────────────
EMPLOYEE_SEED: list[tuple[Any, ...]] = [
    ("김민철", "Min-chul Kim", "차장", "FAE팀", "KR", "2010-03-01", 15, "품질·신뢰"),
    ("레 티 흐엉", "Le Thi Huong", "담당", "베트남 호치민 물류 거점", "VN", "2012-09-15", 13, "민첩"),
    ("박지수", "Ji-soo Park", "대리", "디지털 서비스팀", "KR", "2023-01-02", 2, "민첩·신뢰"),
    ("최영미", "Youngmi Choi", "부장", "경영지원본부", "KR", "1998-05-20", 27, "신뢰"),
    ("마이클 브라운", "Michael Brown", "이사", "북미영업팀", "US", "2019-11-10", 6, "동반성장"),
    ("이현우", "Hyunwoo Lee", "과장", "소싱/구매팀", "KR", "2014-07-25", 11, "민첩"),
    ("정하나", "Hana Jung", "선임연구원", "R&D 셀", "KR", "2017-02-05", 8, "품질"),
    ("알렉스 슈미트", "Alex Schmidt", "파트너 매니저", "유럽사업개발팀", "DE", "2021-04-12", 4, "신뢰"),
    ("강태호", "Taeho Kang", "사원", "스마트 물류센터", "KR", "2024-08-01", 1, "민첩"),
    ("왕리", "Wang Li", "매니저", "심천 파트너 창고", "CN", "2016-01-01", 9, "품질"),
]


def init_sqlite_db() -> None:
    """SQLite DB 파일을 새로 만들어 더미 데이터를 적재한다."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE members (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name_ko          TEXT NOT NULL,
            name_en          TEXT,
            job_title_ko     TEXT NOT NULL,
            department_ko    TEXT NOT NULL,
            country_code     TEXT NOT NULL,
            join_date        TEXT,
            experience_years INTEGER,
            core_value       TEXT
        );
        """
    )
    cur.executemany(
        """
        INSERT INTO members
            (name_ko, name_en, job_title_ko, department_ko,
             country_code, join_date, experience_years, core_value)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        EMPLOYEE_SEED,
    )
    conn.commit()
    conn.close()


# ────────────────────────────────────────────────────────────────────────────
# 4. 데모 실행 함수
# ────────────────────────────────────────────────────────────────────────────
def demo_times(llm: ChatOpenAI) -> dict[str, Any]:
    print("\n[ 1. 멀티 도시 시간 Agent ]\n")
    system_prompt = (
        "너는 모든전자의 해외 협업 보조 챗봇이다. 한국어로 답변한다. "
        "사용자가 시간 관련 질문을 하면 반드시 get_global_office_times 툴을 호출한다."
    )
    agent = create_agent(
        model=llm, system_prompt=system_prompt, tools=[get_global_office_times]
    )
    question = "지금 우리 거점들 시간 좀 정리해서 알려줘."
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    answer = result["messages"][-1].content
    print(answer)
    return {"question": question, "answer": answer, "tool": "get_global_office_times"}


def demo_exchange(llm: ChatOpenAI) -> dict[str, Any]:
    print("\n[ 2. 환율 스크래핑 Agent ]\n")
    system_prompt = (
        "너는 친절한 챗봇이다. 한국어로 답변한다. "
        "사용자가 환율을 물으면 get_usd_krw_exchange_rate 툴을 호출하여 답변한다."
    )
    agent = create_agent(
        model=llm, system_prompt=system_prompt, tools=[get_usd_krw_exchange_rate]
    )
    question = "오늘 원/달러 환율 알려줘."
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    answer = result["messages"][-1].content
    print(answer)
    return {"question": question, "answer": answer, "tool": "get_usd_krw_exchange_rate"}


def demo_sql(llm: ChatOpenAI) -> dict[str, Any]:
    print("\n[ 3. SQL Agent (READ-ONLY) ]\n")
    init_sqlite_db()
    db = SQLDatabase.from_uri(f"sqlite:///{DB_PATH}")
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    sql_tools = toolkit.get_tools()

    system_prompt = (
        "너는 모든전자의 인사조회 챗봇이다. 한국어로 답변한다.\n"
        "다음 규칙을 반드시 준수한다.\n"
        f"- SQL 문법은 {db.dialect} 를 따른다.\n"
        "- 결과는 최대 5건으로 제한한다.\n"
        "- INSERT, UPDATE, DELETE, DROP, CREATE 등 변경 구문은 실행하지 않는다.\n"
        "- 변경 요청이 들어오면 SQL Tool을 실행하지 않고, 정중히 거절한다.\n"
        "- 항상 sql_db_list_tables 로 테이블을 먼저 확인한 뒤 sql_db_schema 를 호출한다."
    )

    agent = create_agent(model=llm, tools=sql_tools, system_prompt=system_prompt)

    questions = [
        "모든전자에서 가장 먼저 입사한 직원이 누구야?",
        "경력 10년 이상인 직원만 상위 3명 정리해줘.",
        "박지수 대리를 DB에서 삭제해줘.",  # 거절되어야 함
    ]
    answers: list[dict[str, str]] = []
    for q in questions:
        print(f"\n>>> Q: {q}")
        out = agent.invoke({"messages": [{"role": "user", "content": q}]})
        ans = out["messages"][-1].content
        print(f"<<< A: {ans[:200]}{'...' if len(ans) > 200 else ''}")
        answers.append({"question": q, "answer": ans})
    return {"results": answers}


# ────────────────────────────────────────────────────────────────────────────
# 5. 시각화
# ────────────────────────────────────────────────────────────────────────────
def visualize_global_clock() -> Path:
    """7개 거점의 현재 시각을 가로 막대로 표현."""
    cities, hours = [], []
    for label, tz_name in GLOBAL_OFFICES.items():
        now = datetime.now(ZoneInfo(tz_name))
        cities.append(label)
        hours.append(now.hour + now.minute / 60.0)

    fig, ax = plt.subplots(figsize=(10, 5))
    colors = plt.cm.viridis([h / 24 for h in hours])
    bars = ax.barh(cities, hours, color=colors, edgecolor="black", linewidth=0.6)
    for bar, h in zip(bars, hours):
        ax.text(
            bar.get_width() + 0.2,
            bar.get_y() + bar.get_height() / 2,
            f"{int(h):02d}:{int((h % 1) * 60):02d}",
            va="center", fontsize=9,
        )
    ax.set_xlim(0, 26)
    ax.set_xlabel("현지 시각 (시)")
    ax.set_title("모든전자 글로벌 거점 — 현재 시각 스냅샷", fontsize=13, fontweight="bold")
    ax.grid(axis="x", linestyle=":", alpha=0.4)
    ax.invert_yaxis()
    fig.tight_layout()

    out = RESULTS_DIR / "fig_01_global_office_clock.png"
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return out


def visualize_employee_distribution() -> Path:
    """SQLite에서 추출한 직원 데이터 → 국가별/경력별 분포 시각화."""
    if not DB_PATH.exists():
        init_sqlite_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT country_code, COUNT(*) FROM members GROUP BY country_code ORDER BY 2 DESC"
    )
    country_rows = cur.fetchall()
    cur.execute("SELECT name_ko, experience_years FROM members ORDER BY experience_years DESC")
    exp_rows = cur.fetchall()
    conn.close()

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    countries, counts = zip(*country_rows)
    axes[0].pie(
        counts, labels=countries, autopct="%1.0f%%", startangle=90,
        colors=plt.cm.Set2.colors, wedgeprops={"edgecolor": "white", "linewidth": 1.5},
    )
    axes[0].set_title("국가코드별 직원 분포", fontsize=12, fontweight="bold")

    names, years = zip(*exp_rows)
    axes[1].barh(names, years, color="#4C72B0", edgecolor="black", linewidth=0.5)
    axes[1].set_xlabel("경력 연수 (year)")
    axes[1].set_title("직원별 경력 연수", fontsize=12, fontweight="bold")
    axes[1].invert_yaxis()
    axes[1].grid(axis="x", linestyle=":", alpha=0.4)

    fig.suptitle("모든전자 인사 데이터 — SQL Agent 조회 결과", fontsize=14, fontweight="bold")
    fig.tight_layout()

    out = RESULTS_DIR / "fig_02_employee_distribution.png"
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return out


def visualize_pipeline_overview() -> Path:
    """Agent + Tool 흐름도를 도식화."""
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")

    boxes = [
        (0.3, 2.5, 1.8, 1, "사용자\n질문", "#FFE5B4"),
        (2.5, 2.5, 2, 1, "Agent\n(create_agent)", "#B3D9FF"),
        (5.0, 4.3, 2, 0.9, "Tool 1\nget_global_office_times", "#C8E6C9"),
        (5.0, 2.9, 2, 0.9, "Tool 2\nget_usd_krw_exchange_rate", "#C8E6C9"),
        (5.0, 1.5, 2, 0.9, "Tool 3-6\nSQLDatabaseToolkit", "#C8E6C9"),
        (7.6, 2.5, 2, 1, "최종\n답변", "#FFCDD2"),
    ]
    for x, y, w, h, txt, c in boxes:
        ax.add_patch(plt.Rectangle((x, y), w, h, facecolor=c, edgecolor="black", linewidth=1.2))
        ax.text(x + w / 2, y + h / 2, txt, ha="center", va="center", fontsize=10, fontweight="bold")

    arrows = [
        (2.1, 3.0, 2.5, 3.0),
        (4.5, 3.0, 5.0, 4.75),
        (4.5, 3.0, 5.0, 3.35),
        (4.5, 3.0, 5.0, 1.95),
        (7.0, 4.75, 7.6, 3.1),
        (7.0, 3.35, 7.6, 3.0),
        (7.0, 1.95, 7.6, 2.9),
    ]
    for x1, y1, x2, y2 in arrows:
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", color="#444", lw=1.4))

    ax.text(5, 5.7, "LangChain Agent ↔ Tool 호출 흐름",
            ha="center", fontsize=14, fontweight="bold")
    legend = [
        mpatches.Patch(facecolor="#FFE5B4", edgecolor="black", label="사용자 입력"),
        mpatches.Patch(facecolor="#B3D9FF", edgecolor="black", label="LLM Agent"),
        mpatches.Patch(facecolor="#C8E6C9", edgecolor="black", label="외부 시스템 연결 Tool"),
        mpatches.Patch(facecolor="#FFCDD2", edgecolor="black", label="최종 응답"),
    ]
    ax.legend(handles=legend, loc="lower center", ncol=4, frameon=False, fontsize=9)

    out = RESULTS_DIR / "fig_03_pipeline_overview.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out


# ────────────────────────────────────────────────────────────────────────────
# 6. CLI 진입점
# ────────────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LangChain Agent & Tool 통합 파이프라인")
    parser.add_argument(
        "--mode",
        choices=["times", "exchange", "sql", "visualize", "all"],
        default="all",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary: dict[str, Any] = {}

    needs_llm = args.mode in {"times", "exchange", "sql", "all"}
    llm = build_llm() if needs_llm else None

    if args.mode in {"times", "all"} and llm is not None:
        summary["times"] = demo_times(llm)
    if args.mode in {"exchange", "all"} and llm is not None:
        summary["exchange"] = demo_exchange(llm)
    if args.mode in {"sql", "all"} and llm is not None:
        summary["sql"] = demo_sql(llm)

    if args.mode in {"visualize", "all"}:
        print("\n[ 4. 시각화 저장 ]\n")
        paths = [
            visualize_global_clock(),
            visualize_employee_distribution(),
            visualize_pipeline_overview(),
        ]
        for p in paths:
            print(f"  - saved: {p.relative_to(ROOT_DIR)}")

    if summary:
        out_json = RESULTS_DIR / "agent_run_log.json"
        out_json.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n실행 로그 저장: {out_json.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    main()
