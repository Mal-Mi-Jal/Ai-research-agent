import os
from dotenv import load_dotenv
from typing import TypedDict
from pydantic import BaseModel
from langgraph.graph import StateGraph, START, END
from langchain_anthropic import ChatAnthropic
from langchain_tavily import TavilySearch

load_dotenv()

# torch + chromadb (memory.py's deps) don't fit in Render free tier's 512MB
# RAM, so hosted deploys set MEMORY_ENABLED=false to skip importing them
# entirely. CLI/MCP usage keeps the caching feature by default.
MEMORY_ENABLED = os.getenv("MEMORY_ENABLED", "true").lower() == "true"

if MEMORY_ENABLED:
    import memory

llm = ChatAnthropic(model="claude-sonnet-5")
search = TavilySearch(max_results=5)


class AgentState(TypedDict):
    question: str
    search_results: list
    summary: str
    report: str


class RelevanceCheck(BaseModel):
    relevant_indices: list[int]


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


def search_node(state: AgentState) -> dict:
    result = search.invoke(state["question"])
    return {"search_results": result["results"]}


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


def write_node(state: AgentState) -> dict:
    prompt = f"""다음 정리된 자료를 바탕으로 "{state['question']}"에 대한 리포트 본문을 작성해줘.

정리된 자료:
{state['summary']}

- 3~5개의 소제목으로 구성해줘
- 각 섹션은 2~3문장으로 간결하게
- 본문 내용에 참고한 출처 번호를 [1], [2] 형식으로 인용해줘
- 출처 URL 목록은 작성하지 마 (별도로 붙일 거야)"""
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
graph.add_node("summarize", summarize_node)
graph.add_node("write", write_node)

if MEMORY_ENABLED:
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
    graph.add_edge(START, "search")
    graph.add_edge("write", END)

graph.add_edge("search", "verify")
graph.add_edge("verify", "summarize")
graph.add_edge("summarize", "write")

app = graph.compile()


if __name__ == "__main__":
    question = input("조사할 주제를 입력하세요: ")
    result = app.invoke({"question": question})
    print("\n=== 리포트 ===\n")
    print(result["report"])
