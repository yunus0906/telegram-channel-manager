$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$python = Join-Path $backendRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
  throw '未找到 backend/.venv。请先在 backend 目录执行 uv sync --frozen --extra test。'
}
Set-Location -LiteralPath $backendRoot
& $python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
