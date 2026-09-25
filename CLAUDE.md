# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python -m venv venv
source venv/Scripts/activate      # Windows Git Bash (PowerShell: .\venv\Scripts\Activate.ps1)
pip install -r requirements.txt
cp .env.example .env              # fill in ANTHROPIC_API_KEY and TAVILY_API_KEY

# Run the agent directly (CLI, prompts for a topic)
python agent.py

# Run as an MCP server (stdio transport)
python mcp_server.py
python test_mcp_client.py         # minimal stdio client that exercises it

# Run as an HTTP API for n8n / other callers
uvicorn api:app --port 8000       # POST /research {"topic": "..."}

# n8n automation
npx n8n                                          # start n8n (first run installs it)
npx n8n import:workflow --input=workflow.json    # schedule -> HTTP Request -> Markdown -> Send Email (SMTP)

# Local Docker build (mirrors the Render deploy)
docker build -t ai-research-agent .
docker run -p 7860:7860 --env-file .env -e MEMORY_ENABLED=false ai-research-agent
```

There is no test suite or linter. `test_search.py`, `test_mcp_client.py` and `hello_agent.py` are manual smoke scripts that hit the real (paid) Tavily/Claude APIs. To exercise a single node without API calls, patch `agent.search.invoke` / `agent.llm` and call the node function directly.

- `ModuleNotFoundError: No module named 'dotenv'` (or any project dep) with a traceback through `...\Python314\Scripts\uvicorn.exe` means the venv isn't active — the global Python ran instead.
- On Windows terminals, force UTF-8 output when running any script that prints Korean text, or it renders as mojibake: `PYTHONIOENCODING=utf-8 python agent.py`.
- `uvicorn` isn't started with `--reload`; restart it after code changes before testing through n8n.

## Architecture

The core is a single LangGraph `StateGraph` in `agent.py` (`AgentState`: `question`, `search_results`, `summary`, `sections`, `report`). Every entry point wraps this same compiled graph (`app = graph.compile()`), not a separate implementation:

- `api.py` — FastAPI, for n8n / HTTP callers
- `mcp_server.py` — MCP tool (`research`) over stdio, for MCP clients
- `agent.py __main__` — direct CLI

Supporting modules, all imported only when `MEMORY_ENABLED` is truthy (they pull in torch/chromadb):
- `embedding.py` — the one embedding model shared by the two below (loaded once)
- `memory.py` — question cache (`check_memory` / `save_memory` nodes)
- `rag.py` — chunking + per-run vector retrieval (`retrieve` node)

Graph flow — the shape depends on `MEMORY_ENABLED`, decided at import time:
```
MEMORY_ENABLED=true (local default):
START -> check_memory --(cache_hit)--> END
                        --(cache_miss)--> search -> verify -> plan -> retrieve -> write -> save_memory -> END
MEMORY_ENABLED=false (Render):
START -> search -> verify -> summarize -> write -> END
```

- `search` dedupes Tavily results by URL-decoded URL (Tavily can return the same post once with a Korean path and once percent-encoded). With `MEMORY_ENABLED` it also requests `raw_content` (full page text) for RAG.
- `verify` uses `llm.with_structured_output(RelevanceCheck)` to drop irrelevant results before `plan` / `summarize`.
- RAG path: `plan` has the LLM produce 3–5 section headings, each with a retrieval query. `retrieve` (`rag.retrieve_evidence`) chunks each source's raw text (300 chars, 50 overlap, first 10k chars per source), embeds them into a throwaway in-memory Chroma collection, and runs MMR search per section query; each chunk carries its source number so `write` cites `[n]` against actual page text. `write_node` picks the RAG prompt when `state["sections"]` is set, else the summary prompt.
- `write` generates report body text only; the source URL list is appended afterward from `state["search_results"]` in Python (as a Markdown `- ` list so n8n's Markdown→HTML step puts each on its own line), not by the LLM — avoids citation hallucination.
- `embedding.py` uses `paraphrase-multilingual-MiniLM-L12-v2`. The previous `all-MiniLM-L6-v2` is English-only and can't separate Korean text ("신입 개발자 채용 트렌드" vs "반도체 산업 전망" scored 0.93 — a false cache hit at the old 0.85 threshold). The multilingual model truncates at 128 tokens (~300 Korean chars), which is what `rag.CHUNK_SIZE` is sized to.
- `memory.py` embeds the **question** (not the report) and compares against past questions in a Chroma store (`./chroma_db`, gitignored, collection `research_questions_multilingual`) using cosine similarity, `SIMILARITY_THRESHOLD = 0.92`. A hit skips the whole search→write chain — the main lever for avoiding redundant Claude/Tavily calls, so keep embedding the question side, not the report side.
  - The threshold was measured on Korean question pairs: paraphrases score 0.75–0.99, different questions 0.37–0.90, and the ranges overlap. It sits above the highest different-question score on purpose: a false hit returns the wrong report, a false miss only costs an extra run.
  - Changing the embedding model invalidates stored vectors: use a new collection name and re-embed the old questions (stored as documents, reports in metadata).
- `extract_text()` in `agent.py` unwraps `ChatAnthropic` responses: Claude Sonnet 5's adaptive thinking can return `response.content` as a list of `{type, text}` blocks instead of a plain string. Any new node that reads `response.content` directly must go through `extract_text()` or it will leak raw thinking-block dicts into output.
- **stdio MCP servers must never `print()` to stdout** — stdout *is* the JSON-RPC channel in `mcp_server.py`. `memory.py` / `rag.py` log to `sys.stderr` for this reason; keep any new logging there too.

Model: `claude-sonnet-5` (chosen for cost; not the skill-default `claude-opus-5`, since this is a budget-conscious side project). `hello_agent.py` still pins an older model id; it's a standalone first-steps script, not used by the graph.

## n8n workflow (`workflow.json`)

- The Send Email node uses Gmail SMTP (`smtp.gmail.com:465`, SSL) + a Gmail app password, not the Gmail API node: Gmail OAuth needs a Google Cloud project, which pushed the user into a paid billing signup. n8n shows "Couldn't connect … No testing function found" for SMTP credentials — that's not a failure, SMTP creds just have no test; execute the workflow to verify.
- The node ships without credentials and with a `YOUR_EMAIL@gmail.com` placeholder (so no personal address gets committed) — both are set in the n8n UI after import. Topic edits made in the n8n UI live in n8n's DB, not in `workflow.json`; re-importing resets them.
- `api.py` must already be running on port 8000. On Windows, n8n (Node) resolves `localhost` to the IPv6 loopback first; uvicorn only listens on IPv4, so the HTTP Request node must target `127.0.0.1`, not `localhost`.
- The local n8n owner account lives in `~/.n8n/database.sqlite`; if the login is forgotten, `npx n8n user-management:reset` (with n8n stopped) re-runs owner setup and keeps workflows.

## Deployment (Render, free tier)

Live at https://ai-research-agent-ctjj.onrender.com. Required env vars: `ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, `MEMORY_ENABLED=false`. Source repo: GitHub `Mal-Mi-Jal/Ai-research-agent`, branch `main`.

`MEMORY_ENABLED=false` is not optional on the free instance — it's a hard requirement, not a tuning knob:
- Render free web services have 512MB RAM. The imports behind `embedding.py` / `memory.py` / `rag.py` (`torch` via `sentence-transformers`, `chromadb`) don't fit alongside the rest of the process; the container gets OOM-killed before `uvicorn` can bind a port.
- `agent.py` only imports `memory` / `rag` when `MEMORY_ENABLED` is truthy, so setting it to `false` keeps torch out of the import graph entirely rather than just skipping nodes at runtime. That also means Render serves the snippet-summary path, not RAG.
- The Dockerfile `COPY`s source files by name — add any new module there, or local `docker run` with memory enabled will fail on import.
- The Dockerfile binds to `${PORT:-7860}` (shell form `CMD`, not exec form) because Render assigns the port via the `PORT` env var (default 10000) and fails the deploy if nothing is listening on it within a timeout.
- `requirements.txt` is a curated list of direct dependencies, not a `pip freeze` dump — freeze pulled in `pywin32` (Windows-only, no Linux wheel) and version pins with Python-version markers (e.g. `networkx==3.7` needing `>=3.12`) that didn't match the Docker base image at the time. If regenerating it, keep it to direct imports only, or verify every pin actually installs on `python:3.14-slim`.
- The Docker base image's Python version must match whatever version actually resolved the pins in `requirements.txt` (currently 3.14) — a mismatch surfaces as "no matching distribution" errors that look unrelated to the real cause.
