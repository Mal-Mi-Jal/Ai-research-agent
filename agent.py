import os
from urllib.parse import unquote
from dotenv import load_dotenv
from typing import TypedDict
from pydantic import BaseModel
from langgraph.graph import StateGraph, START, END
from langchain_anthropic import ChatAnthropic
from langchain_tavily import TavilySearch

load_dotenv()

# torch + chromadb (memory.py / rag.py deps) don't fit in Render free tier's
# 512MB RAM, so hosted deploys set MEMORY_ENABLED=false to skip importing them
# entirely. That disables both the question cache and RAG; the graph then falls
# back to summarizing Tavily's short snippets. CLI/MCP usage keeps both on by default.
MEMORY_ENABLED = os.getenv("MEMORY_ENABLED", "true").lower() == "true"

if MEMORY_ENABLED:
    import memory
    import rag

llm = ChatAnthropic(model="claude-sonnet-5")
# RAG는 웹페이지 원문 전체를 조각내서 쓰므로, 켜져 있을 때만 원문을 받아온다
search = TavilySearch(max_results=5, include_raw_content=MEMORY_ENABLED)


class AgentState(TypedDict):
    question: str
    search_results: list
    summary: str
    sections: list
    report: str


class RelevanceCheck(BaseModel):
    relevant_indices: list[int]


class SectionPlan(BaseModel):
    heading: str
    query: str


class Outline(BaseModel):
    sections: list[SectionPlan]


def extract_text(message) -> str:
    """thinking 모델은 content가 문자열이 아니라 블록 리스트로 올 수 있어서,
    그 중 실제 답변(text) 블록만 골라 이어붙인다."""
    if isinstance(message.content, str):
        return message.content
    return "".join(
        block["text"]
        for block in message.content
        if isinstance(block, dict) and block.get("type") == "text"
    )


def check_memory_node(state: AgentState) -> dict:
    cached = memory.find_similar_report(state["question"])
    if cached is None:
        return {}
    return {"report": f"{cached}\n\n(이전에 조사한 내용을 재사용했어요 - API 호출 없음)"}


def route_after_memory(state: AgentState) -> str:
    return "cache_hit" if state.get("report") else "cache_miss"


def save_memory_node(state: AgentState) -> dict:
    memory.save_report(state["question"], state["report"])
    return {}


def dedupe_by_url(results: list[dict]) -> list[dict]:
    """Tavily가 같은 글을 한글 그대로인 URL과 %인코딩된 URL로 두 번 돌려주는 경우가
    있어서, 디코딩한 URL 기준으로 중복을 제거한다."""
    seen = set()
    unique = []
    for r in results:
        key = unquote(r["url"]).rstrip("/")
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def search_node(state: AgentState) -> dict:
    result = search.invoke(state["question"])
    return {"search_results": dedupe_by_url(result["results"])}


def verify_node(state: AgentState) -> dict:
    sources_text = "\n\n".join(
        f"[{i + 1}] {r['title']}\n{r['content'][:200]}"
        for i, r in enumerate(state["search_results"])
    )
    prompt = f"""다음은 "{state['question']}"에 대한 검색 결과 목록입니다.

{sources_text}

질문과 실제로 관련 있는 출처의 번호만 골라줘. 질문 주제와 무관한 회사/제품 정보, 광고성 내용은 제외해줘."""

    structured_llm = llm.with_structured_output(RelevanceCheck)
    result = structured_llm.invoke(prompt)

    filtered = [
        state["search_results"][i - 1]
        for i in result.relevant_indices
        if 1 <= i <= len(state["search_results"])
    ]
    return {"search_results": filtered}


def summarize_node(state: AgentState) -> dict:
    sources_text = "\n\n".join(
        f"[{i+1}] {r['title']}\n{r['content']}"
        for i, r in enumerate(state["search_results"])
    )
    prompt = f"""다음은 "{state['question']}"에 대한 검색 결과입니다.

{sources_text}

각 출처의 핵심 내용을 번호를 매겨 간결하게 정리해줘. 각 항목 끝에 어느 출처 번호에서 나온 내용인지 표시해줘."""
    response = llm.invoke(prompt)
    return {"summary": extract_text(response)}


def plan_node(state: AgentState) -> dict:
    sources_text = "\n\n".join(
        f"[{i + 1}] {r['title']}\n{r['content'][:200]}"
        for i, r in enumerate(state["search_results"])
    )
    prompt = f"""다음 검색 결과를 바탕으로 "{state['question']}"에 대한 리포트의 목차를 짜줘.

{sources_text}

- 소제목 3~5개
- 각 소제목마다, 원문에서 그 섹션의 근거 문장을 찾을 검색 질의(query)를 한 문장으로 적어줘"""
    outline = llm.with_structured_output(Outline).invoke(prompt)
    return {"sections": [s.model_dump() for s in outline.sections]}


def retrieve_node(state: AgentState) -> dict:
    evidence = rag.retrieve_evidence(
        state["search_results"], [s["query"] for s in state["sections"]]
    )
    return {
        "sections": [
            {**section, "evidence": chunks}
            for section, chunks in zip(state["sections"], evidence)
        ]
    }


def rag_write_prompt(state: AgentState) -> str:
    material = "\n\n".join(
        f"## {s['heading']}\n"
        + "\n".join(f"[{c['source']}] {c['text']}" for c in s["evidence"])
        for s in state["sections"]
    )
    return f"""다음은 "{state['question']}" 리포트의 목차와, 소제목마다 웹페이지 원문에서 찾아온 근거 조각이야. 조각 앞의 [n]은 출처 번호야.

{material}

- 맨 위에 "# 제목" 한 줄을 쓰고, 위 소제목을 순서대로 "## 소제목"으로 써줘
- 각 섹션은 2~3문장으로 간결하게, 그 섹션의 근거 조각에 있는 내용만 사용해줘
- 문장마다 근거가 된 조각의 출처 번호를 [1], [2] 형식으로 인용해줘
- 근거 조각에 없는 수치나 사실은 지어내지 마
- 출처 URL 목록은 작성하지 마 (별도로 붙일 거야)"""


def summary_write_prompt(state: AgentState) -> str:
    return f"""다음 정리된 자료를 바탕으로 "{state['question']}"에 대한 리포트 본문을 작성해줘.

정리된 자료:
{state['summary']}

- 3~5개의 소제목으로 구성해줘
- 각 섹션은 2~3문장으로 간결하게
- 본문 내용에 참고한 출처 번호를 [1], [2] 형식으로 인용해줘
- 출처 URL 목록은 작성하지 마 (별도로 붙일 거야)"""


def write_node(state: AgentState) -> dict:
    # RAG 경로(plan → retrieve)를 거쳤으면 sections가, 아니면 summary가 채워져 있다
    if state.get("sections"):
        prompt = rag_write_prompt(state)
    else:
        prompt = summary_write_prompt(state)
    response = llm.invoke(prompt)

    sources = "\n".join(
        f"- [{i + 1}] {r['title']} - {r['url']}"
        for i, r in enumerate(state["search_results"])
    )
    # 마크다운 목록(- )이어야 HTML 변환 시 출처가 한 줄씩 나뉜다 (n8n 메일 발송)
    report = f"{extract_text(response)}\n\n---\n출처:\n\n{sources}"
    return {"report": report}


graph = StateGraph(AgentState)
graph.add_node("search", search_node)
graph.add_node("verify", verify_node)
graph.add_node("write", write_node)
graph.add_edge("search", "verify")

if MEMORY_ENABLED:
    # RAG: 목차를 먼저 짜고, 소제목마다 원문 조각을 벡터 검색해서 근거로 쓴다
    graph.add_node("plan", plan_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_edge("verify", "plan")
    graph.add_edge("plan", "retrieve")
    graph.add_edge("retrieve", "write")

    graph.add_node("check_memory", check_memory_node)
    graph.add_node("save_memory", save_memory_node)
    graph.add_edge(START, "check_memory")
    graph.add_conditional_edges(
        "check_memory",
        route_after_memory,
        {"cache_hit": END, "cache_miss": "search"},
    )
    graph.add_edge("write", "save_memory")
    graph.add_edge("save_memory", END)
else:
    # Render 무료 티어: 임베딩 없이 Tavily 요약문을 LLM이 정리해서 쓴다
    graph.add_node("summarize", summarize_node)
    graph.add_edge("verify", "summarize")
    graph.add_edge("summarize", "write")

    graph.add_edge(START, "search")
    graph.add_edge("write", END)

app = graph.compile()


if __name__ == "__main__":
    question = input("조사할 주제를 입력하세요: ")
    result = app.invoke({"question": question})
    print("\n=== 리포트 ===\n")
    print(result["report"])
