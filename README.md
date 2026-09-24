# AI Research Agent

주제를 입력하면 조사하고 근거와 함께 리포트를 생성하는 AI 에이전트.

## Stack
- LangGraph — 에이전트 워크플로우 (검색 → 캐시 확인 → 검증 → 요약 → 작성)
- LangChain — LLM 연동 레이어
- Anthropic Claude API — 추론 엔진
- Tavily — 웹 검색
- Chroma + sentence-transformers — 로컬 벡터DB, 과거 질문 캐싱
- MCP — `mcp_server.py`로 에이전트를 표준 도구화
- n8n — `workflow.json`으로 스케줄 자동 실행
- (예정) AWS — 배포

## Setup
\`\`\`bash
python -m venv venv
source venv/Scripts/activate  # Windows Git Bash
pip install -r requirements.txt
cp .env.example .env  # 그리고 .env에 실제 API 키 입력
\`\`\`

## 실행 방법
- CLI로 직접: `python agent.py`
- MCP 서버로: `python mcp_server.py` (표준입출력 기반, MCP 클라이언트에서 `research` 도구로 호출)
- HTTP API로: `uvicorn api:app --port 8000` (`POST /research {"topic": "..."}`)
- n8n 자동화: `npx n8n`으로 n8n 실행 → `npx n8n import:workflow --input=workflow.json`으로 워크플로우 가져오기 (API 서버가 먼저 떠 있어야 함)
