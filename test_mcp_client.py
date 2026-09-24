import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(
    command=sys.executable,
    args=["mcp_server.py"],
)


async def main():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("서버가 제공하는 도구:", [t.name for t in tools.tools])

            result = await session.call_tool(
                "research", {"topic": "2026년 신입 개발자 채용 트렌드"}
            )
            print("\n=== MCP 도구 호출 결과 ===\n")
            print(result.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
