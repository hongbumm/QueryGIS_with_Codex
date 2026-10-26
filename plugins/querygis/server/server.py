"""Expose only task-level control: QueryGIS plans, generates and executes GIS code."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from client import QueryGISClient

server = MCPServer("QueryGIS", instructions=(
    "Use the existing QueryGIS plugin for QGIS work. Submit natural-language goals; its existing "
    "QueryGIS_Flask server owns authentication, AI requests, RAG and code correction. The user's key "
    "is a QueryGIS-issued service key, never an OpenAI/Gemini key. Enter it only in the existing "
    "QGIS panel. This connector forwards tasks and reads outcomes; it has no GIS or AI implementation. "
    "Check connection, reuse request_id on uncertain delivery and poll the same task. "
    "Do not bypass QueryGIS with code, shell, direct project edits or other QGIS controllers."
))
client = QueryGISClient()
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)


@server.tool(annotations=READ)
async def get_connection_status() -> dict:
    """Read connection, existing QueryGIS authentication readiness and cached layers. Never exposes keys."""
    return await asyncio.to_thread(client.status)


@server.tool(annotations=WRITE)
async def submit_task(instruction: str, request_id: str, mode: str = "run") -> dict:
    """Forward a natural-language goal to the existing QueryGIS Ask/Ask and Run workflow.

    Generate a unique request_id for a new task; reuse it if delivery is uncertain. mode is run or ask.
    Uses the same selected-layer context as the existing QGIS panel. No code or key input is supported.
    """
    return await asyncio.to_thread(client.request, "POST", "/tasks", {
        "instruction": instruction, "request_id": request_id, "mode": mode})


@server.tool(annotations=READ)
async def get_task_status(task_id: str) -> dict:
    """Read the forwarded task's state. Poll at a reasonable interval."""
    return await asyncio.to_thread(client.request, "GET", client.task_path(task_id))


@server.tool(annotations=READ)
async def get_task_result(task_id: str) -> dict:
    """Return the existing QueryGIS outcome, execution flag, new layers, messages and errors; keys stay in QGIS."""
    return await asyncio.to_thread(client.request, "GET", client.task_path(task_id))


@server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
async def cancel_task(task_id: str) -> dict:
    """Cancel a queued request or suppress pending responses. Running QGIS code completes before cancellation is reflected."""
    return await asyncio.to_thread(client.request, "POST", client.task_path(task_id) + "/cancel", {})


if __name__ == "__main__":
    server.run(transport="stdio")
