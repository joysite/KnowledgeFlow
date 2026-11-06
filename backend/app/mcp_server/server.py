"""KnowledgeFlow MCP stdio Server。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from app.mcp_server.rag_tool import register_rag_tool
from app.mcp_server.runtime import MCPRuntime
from app.mcp_server.tools import register_tools


@asynccontextmanager
async def app_lifespan(_: FastMCP) -> AsyncIterator[MCPRuntime]:
    """管理 MCP Server 的资源生命周期。"""
    runtime = MCPRuntime()
    await runtime.start()

    try:
        yield runtime
    finally:
        await runtime.close()


server = FastMCP(
    "KnowledgeFlow",
    lifespan=app_lifespan,
)

register_tools(server)
register_rag_tool(server)


def main() -> None:
    """启动 MCP stdio 服务。"""
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
