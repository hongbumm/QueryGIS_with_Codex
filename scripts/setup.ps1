param([string]$PythonCommand = 'python')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $projectRoot '.venv'
if (-not (Test-Path -LiteralPath (Join-Path $venvPath 'Scripts\python.exe'))) {
    & $PythonCommand -m venv $venvPath
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed' }
}
$venvPython = Join-Path $venvPath 'Scripts\python.exe'
& $venvPython -m pip install -r (Join-Path $projectRoot 'requirements-mcp.txt')
if ($LASTEXITCODE -ne 0) { throw 'MCP dependency installation failed' }
& $venvPython (Join-Path $PSScriptRoot 'configure_codex.py')
if ($LASTEXITCODE -ne 0) { throw 'Codex registration failed' }
& $venvPython (Join-Path $PSScriptRoot 'build_plugin.py')
if ($LASTEXITCODE -ne 0) { throw 'QGIS plugin packaging failed' }
& $venvPython (Join-Path $PSScriptRoot 'install_qgis_connector.py')
if ($LASTEXITCODE -ne 0) { throw 'QGIS connector installation failed' }
