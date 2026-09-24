# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python -m venv venv
source venv/Scripts/activate      # Windows Git Bash
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
npx n8n import:workflow --input=workflow.json    # import the schedule -> HTTP Request workflow
# api.py must already be running on port 8000. On Windows, n8n (Node) resolves
# "localhost" to the IPv6 loopback first; uvicorn only listens on IPv4, so the
# HTTP Request node must target 127.0.0.1, not localhost.
```

On Windows terminals, force UTF-8 output when running any script that prints Korean text, or it renders as mojibake:
```bash
PYTHONIOENCODING=utf-8 python agent.py
```

## Architecture

The core is a single LangGraph `StateGraph` in `agent.py` (`AgentState`: `question`, `search_results`, `summary`, `report`). Every other file is a different transport wrapped around this same compiled graph (`app = graph.compile()`), not a separate implementation:

- `api.py` — FastAPI, for n8n / HTTP callers
- `mcp_server.py` — MCP tool (`research`) over stdio, for MCP clients
- `agent.py __main__` — direct CLI

Graph flow:
```
START -> check_memory --(cache_hit)--> END
                        --(cache_miss)--> search -> verify -> summarize -> write -> save_memory -> END
```

- `check_memory` / `save_memory` (in `memory.py`) embed the **question** (not the report) with a local sentence-transformer and compare against past questions in a Chroma store (`./chroma_db`, gitignored) using cosine similarity, threshold `SIMILARITY_THRESHOLD = 0.85` in `memory.py`. A hit skips the entire search/verify/summarize/write chain — this is the main lever for avoiding redundant Claude/Tavily API calls, so keep embedding the question side when touching this file, not the report side.
- `verify` uses `llm.with_structured_output(RelevanceCheck)` to drop irrelevant Tavily results before they reach the summarizer.
- `write` generates report body text only; the source URL list is appended afterward from `state["search_results"]` in Python, not by the LLM — avoids citation hallucination.
- `extract_text()` in `agent.py` unwraps `ChatAnthropic` responses: Claude Sonnet 5's adaptive thinking can return `response.content` as a list of `{type, text}` blocks instead of a plain string once a prompt is complex enough to trigger thinking. Any new node that reads `response.content` directly must go through `extract_text()` or it will leak raw thinking-block dicts into output.
- **stdio MCP servers must never `print()` to stdout** — stdout *is* the JSON-RPC channel in `mcp_server.py`. `memory.py`'s debug logging writes to `sys.stderr` for this reason; keep any new logging there too.

Model: `claude-sonnet-5` (chosen for cost; not the skill-default `claude-opus-5`, since this is a budget-conscious side project).
