"""Real MCP server (official SDK, stdio) used to prove a real session works through the proxy."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

server = FastMCP("cim-proxy-test")


@server.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@server.tool()
def shout(text: str) -> str:
    """Upper-case the text."""
    return text.upper()


if __name__ == "__main__":
    server.run()
