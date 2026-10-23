---
name: querygis-control
description: Control an open QGIS project through QueryGIS task tools. QueryGIS owns all GIS planning, code generation, execution and correction.
---

Use the `querygis_with_codex` MCP tools registered by this repository's setup script.

1. Check `get_connection_status` before each workflow. If disconnected, tell the user to open the QueryGIS with Codex panel and start its connection. If the provider is unconfigured, ask the user to enter their provider API Key in QGIS. Never request it in chat or pass it to an MCP tool.
2. Submit a natural-language GIS goal with a unique `request_id`. Use layer IDs returned by QueryGIS. Reuse the same request ID after uncertain delivery.
3. QueryGIS decides algorithms, code, CRS handling and execution. Never send Python/SQL scripts inside the task instruction. Never use shell commands, direct project-file editing, or a separate QGIS controller to perform the task.
4. Poll the existing task at reasonable intervals. For `awaiting_approval`, tell the user to review the generated code and click the execution button in QGIS. Do not try to approve through another tool.
5. Report actual terminal outcomes. For cancellation of running work, explain that cancellation is cooperative and existing changes may remain. For failures, use QueryGIS's error and correction flow; do not execute replacement GIS code yourself.

The skill package provides instructions only. The MCP connection must be registered separately by `scripts/setup.ps1`. Installing this skill alone does not install Python dependencies or a QGIS plugin.
