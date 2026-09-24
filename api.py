from fastapi import FastAPI
from pydantic import BaseModel

from agent import app as agent_app

app = FastAPI()


class ResearchRequest(BaseModel):
    topic: str


@app.post("/research")
def research(req: ResearchRequest):
    result = agent_app.invoke({"question": req.topic})
    return {"report": result["report"]}
