import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from agent import app as agent_app

app = FastAPI()

# The public demo pays for every run (Claude + Tavily, no cache on Render),
# so cap total runs per day and runs per client IP. Counts live in memory and
# reset when the instance restarts - good enough to stop casual abuse.
DAILY_LIMIT = int(os.getenv("DEMO_DAILY_LIMIT", "10"))
IP_LIMIT = int(os.getenv("DEMO_IP_LIMIT", "2"))
IP_WINDOW_SECONDS = int(os.getenv("DEMO_IP_WINDOW_SECONDS", "3600"))

_lock = threading.Lock()
_day = None
_day_count = 0
_ip_times = defaultdict(deque)


class ResearchRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=200)


def _client_ip(request: Request) -> str:
    # Render sits behind a proxy; the first X-Forwarded-For entry is the client
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _reserve_run(ip: str) -> None:
    global _day, _day_count
    now = time.time()
    today = datetime.now(timezone.utc).date()
    with _lock:
        if _day != today:
            _day, _day_count = today, 0
        if _day_count >= DAILY_LIMIT:
            raise HTTPException(429, "오늘 데모 실행 한도를 모두 사용했습니다. 내일 다시 시도해 주세요.")
        times = _ip_times[ip]
        while times and times[0] <= now - IP_WINDOW_SECONDS:
            times.popleft()
        if len(times) >= IP_LIMIT:
            raise HTTPException(429, "같은 곳에서 너무 많이 요청했습니다. 잠시 후 다시 시도해 주세요.")
        # Count before running: a failed run may already have spent credits
        _day_count += 1
        times.append(now)


@app.post("/research")
def research(req: ResearchRequest, request: Request):
    _reserve_run(_client_ip(request))
    result = agent_app.invoke({"question": req.topic})
    return {"report": result["report"]}
