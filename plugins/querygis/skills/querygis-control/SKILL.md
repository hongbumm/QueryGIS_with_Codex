---
name: querygis-control
description: Request GIS work through the existing QueryGIS plugin and QueryGIS_Flask server, then inspect its progress and results.
---

Use this plugin's QueryGIS MCP tools. The user key is issued by QueryGIS for its service. AI-provider credentials and model selection belong to the existing QueryGIS_Flask server.

1. Check `get_connection_status`. If disconnected, have the user sign in with Google on an active Pro plan in QueryGIS and choose **Connect with Codex** in the QueryGIS settings, then check the connection again. For a legacy standalone connector, follow its existing connection instructions. Never ask for OpenAI/Gemini keys or collect service keys in chat.
2. Submit a natural-language GIS goal with a unique `request_id`. QueryGIS uses its existing selected-layer context. Reuse the same request ID after uncertain delivery.
3. QueryGIS decides algorithms, code, CRS handling and execution. Never send Python/SQL scripts inside the task instruction. Never use shell commands, direct project-file editing, or a separate QGIS controller to perform the task.
4. Use `mode=ask` for the existing Ask workflow and `mode=run` for Ask and Run. Poll the same task at reasonable intervals. The connector introduces no additional analysis mode or model selection.
5. Report actual terminal outcomes and the `executed` flag. A successful Ask response does not mean GIS code ran. Cancelling prevents pending responses from starting code; a running QGIS operation may finish and retain changes. Existing QueryGIS owns retries and corrections; do not resubmit a failed mutation automatically.

The bundled MCP adapter needs the Python runtime prepared by `scripts/setup.ps1`. The QGIS connector ZIP is a companion to the separately installed original QueryGIS; it does not replace it.
