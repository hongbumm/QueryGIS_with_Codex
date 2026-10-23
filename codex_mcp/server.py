"""Expose only task-level control: QueryGIS plans, generates and executes GIS code."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from codex_mcp.client import QueryGISClient

server = MCPServer("QueryGIS with Codex", instructions=(
    "Use QueryGIS for every QGIS operation. Submit natural-language GIS goals; QueryGIS alone "
    "chooses algorithms, generates code, executes, and validates. Never send Python/SQL code or "
    "provider API keys. Check connection first. Reuse request_id on retries, poll task state, "
    "and report results only after success. awaiting_approval requires action in the QGIS panel. "
    "Do not bypass QueryGIS using shell commands, other QGIS tools, or direct file editing."
))
client = QueryGISClient()
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)


@server.tool(annotations=READ)
async def get_connection_status() -> dict:
    """Read QueryGIS connection, provider readiness and its cached layer IDs/CRS. Never exposes API keys."""
    return await asyncio.to_thread(client.status)


@server.tool(annotations=WRITE)
async def submit_task(instruction: str, request_id: str, layer_ids: list[str] | None = None,
                      mode: str = "run") -> dict:
    """Ask QueryGIS to plan and perform a GIS task. Use plain-language goals, never executable code.

    Generate a unique request_id for a new task; reuse it if delivery is uncertain. mode is run or ask.
    Optional layer_ids must come from get_connection_status. No API key or code input is supported.
    """
    return await asyncio.to_thread(client.request, "POST", "/tasks", {
        "instruction": instruction, "request_id": request_id, "layer_ids": layer_ids or [], "mode": mode})


@server.tool(annotations=READ)
async def get_task_status(task_id: str) -> dict:
    """Read task state. Poll at a reasonable interval. awaiting_approval needs the QGIS user's action."""
    return await asyncio.to_thread(client.request, "GET", client.task_path(task_id))


@server.tool(annotations=READ)
async def get_task_result(task_id: str) -> dict:
    """Return QueryGIS's outcome, output layer IDs, stdout and errors; code and provider secrets stay in QGIS."""
    return await asyncio.to_thread(client.request, "GET", client.task_path(task_id))


@server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
async def cancel_task(task_id: str) -> dict:
    """Request cancellation. Queued/planning/review tasks cancel immediately; running work cancels cooperatively."""
    return await asyncio.to_thread(client.request, "POST", client.task_path(task_id) + "/cancel", {})


if __name__ == "__main__":
    server.run(transport="stdio")
