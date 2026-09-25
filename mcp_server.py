"""리서치 에이전트를 MCP 서버로 노출한다 (stdio).

도구(tool)는 행동, 리소스(resource)는 읽기 전용 데이터로 나눴다:
- research      : 전체 파이프라인 (검색 → 검증 → RAG → 리포트)
- web_search    : 검색 결과만 빠르게 (LLM 호출 없음)
- save_report   : 리포트를 reports/*.md로 저장
- list_reports  : 저장된 리포트 목록
- report://{filename} : 저장된 리포트 본문 (리소스)

stdout이 곧 JSON-RPC 통신 채널이므로 이 프로세스에서는 절대 print()하지 않는다.
"""
import re
from pathlib import Path

from langchain_tavily import TavilySearch
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from agent import app, dedupe_by_url

# MCP 클라이언트마다 서버를 띄우는 작업 폴더(cwd)가 달라서, 이 파일 기준 경로를 쓴다
REPORTS_DIR = Path(__file__).parent / "reports"

mcp = MCPServer("research-agent")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
def research(topic: str) -> str:
    """주어진 주제에 대해 웹을 조사하고, 출처가 달린 마크다운 리포트를 생성한다.
    검색·검증·근거 검색·작성까지 LLM을 여러 번 호출하므로 30초~1분 걸린다.
    비슷한 주제를 이전에 조사했다면 저장된 리포트를 즉시 돌려준다."""
    result = app.invoke({"question": topic})
    return result["report"]


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
def web_search(query: str, max_results: int = 5) -> list[dict]:
    """웹을 검색해서 제목, URL, 요약문 목록만 돌려준다. LLM을 호출하지 않아 빠르고 저렴하다.
    리포트까지 필요 없고 최신 자료만 훑어볼 때 research 대신 쓴다."""
    max_results = max(1, min(max_results, 10))
    result = TavilySearch(max_results=max_results).invoke(query)
    return [
        {"title": r["title"], "url": r["url"], "snippet": r["content"]}
        for r in dedupe_by_url(result["results"])
    ]


def _safe_filename(name: str) -> str:
    """클라이언트가 준 이름에서 경로 구분자·특수문자를 제거한다.
    "../../etc/passwd" 같은 이름으로 reports/ 밖에 쓰는 것(경로 조작)을 막는다."""
    stem = Path(name).stem if name.endswith(".md") else Path(name).name
    stem = re.sub(r"[^\w\s-]", "", stem).strip()
    stem = re.sub(r"\s+", "_", stem)[:80]
    return f"{stem or 'report'}.md"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
def save_report(filename: str, content: str) -> str:
    """리포트(마크다운)를 서버의 reports/ 폴더에 저장하고, 저장된 파일 이름을 돌려준다.
    같은 이름이 있으면 덮어쓰지 않고 _2, _3을 붙인다. 저장한 파일은 report://{파일 이름}으로 읽을 수 있다."""
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / _safe_filename(filename)
    n = 2
    while path.exists():
        path = REPORTS_DIR / f"{Path(_safe_filename(filename)).stem}_{n}.md"
        n += 1
    path.write_text(content, encoding="utf-8")
    return path.name


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_reports() -> list[str]:
    """reports/ 폴더에 저장된 리포트 파일 이름 목록 (최신순)."""
    if not REPORTS_DIR.exists():
        return []
    files = sorted(REPORTS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.name for p in files]


@mcp.resource("report://{filename}", mime_type="text/markdown")
def read_report(filename: str) -> str:
    """저장된 리포트 본문."""
    path = (REPORTS_DIR / filename).resolve()
    if path.parent != REPORTS_DIR.resolve() or not path.is_file():
        raise ValueError(f"리포트를 찾을 수 없어요: {filename}")
    return path.read_text(encoding="utf-8")


if __name__ == "__main__":
    mcp.run()
