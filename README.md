# AI Research Agent

주제를 입력하면 조사하고 근거와 함께 리포트를 생성하는 AI 에이전트.

**Live demo**: https://ai-research-agent-ctjj.onrender.com/docs (`POST /research {"topic": "..."}`, 무료 티어라 비활성 시 슬립 → 첫 요청은 콜드스타트로 느릴 수 있음)

## Stack
- LangGraph — 에이전트 워크플로우 (검색 → 캐시 확인 → 검증 → 요약 → 작성)
- LangChain — LLM 연동 레이어
- Anthropic Claude API — 추론 엔진
- Tavily — 웹 검색
- Chroma + sentence-transformers — 로컬 벡터DB, 과거 질문 캐싱 (`MEMORY_ENABLED=false`로 끌 수 있음)
- MCP — `mcp_server.py`로 에이전트를 표준 도구화
- n8n — `workflow.json`으로 스케줄 자동 실행
- Docker + Render — 배포

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

## 배포 (Render)
1. `Dockerfile` 기준으로 Render Web Service 생성 (Language: Docker)
2. Environment Variables: `ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, `MEMORY_ENABLED=false`
   - 무료 인스턴스는 RAM 512MB라 `MEMORY_ENABLED=true`면 torch/chromadb 로딩 중 OOM 발생
3. 포트는 Render가 주입하는 `$PORT`에 바인딩 (Dockerfile CMD에서 처리)
