# AI Research Agent

주제를 입력하면 조사하고 근거와 함께 리포트를 생성하는 AI 에이전트.

## Stack
- LangGraph — 에이전트 워크플로우 (검색 → 요약 → 검증 → 작성)
- LangChain — LLM 연동 레이어
- Anthropic Claude API — 추론 엔진
- (예정) VectorDB — 근거 문서 임베딩/검색
- (예정) MCP — 도구 표준화
- (예정) n8n — 정기 실행 자동화
- (예정) AWS — 배포

## Setup
\`\`\`bash
python -m venv venv
source venv/Scripts/activate  # Windows Git Bash
pip install -r requirements.txt
cp .env.example .env  # 그리고 .env에 실제 API 키 입력
\`\`\`
