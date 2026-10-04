import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Protocol

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from airp.core.models import Snapshot, Target
from airp.core.security import Forbidden
from airp.mcp.server import TOOLS


class EvidenceReader(Protocol):
    def snapshot(self, target: Target) -> Snapshot: ...


class MCPReader:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()

    async def call(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool not in TOOLS:
            raise Forbidden("Tool is not allowlisted")
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "airp.mcp.server"],
            env={"AIRP_EVIDENCE_FILE": str(self.path)},
        )
        async with asyncio.timeout(15):
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool, arguments)
                    if result.isError:
                        raise Forbidden("MCP evidence request failed")
                    texts = [part.text for part in result.content if part.type == "text"]
                    payload = "".join(texts)
                    if len(payload) > 256_000:
                        raise ValueError("MCP response exceeds size limit")
                    value = json.loads(payload)
                    if not isinstance(value, dict):
                        raise ValueError("MCP response must be an object")
                    return value

    def snapshot(self, target: Target) -> Snapshot:
        return Snapshot.model_validate(asyncio.run(self.call("workload", target.model_dump())))
