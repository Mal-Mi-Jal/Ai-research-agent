from mcp.server.mcpserver import MCPServer
from agent import app

mcp = MCPServer("research-agent")


@mcp.tool()
def research(topic: str) -> str:
    """주어진 주제에 대해 웹을 조사하고, 출처가 달린 리포트를 생성한다."""
    result = app.invoke({"question": topic})
    return result["report"]


if __name__ == "__main__":
    mcp.run()
