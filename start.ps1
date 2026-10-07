param([int]$Port = 8765, [string]$ListenAddress = "127.0.0.1")
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if (!(Test-Path -LiteralPath "web/dist/index.html")) {
    throw "请在 web 目录执行 npm install 和 npm run build"
}
python -X utf8 -m uvicorn website.app:app --host $ListenAddress --port $Port --no-access-log
if ($LASTEXITCODE -ne 0) { throw "公交网站服务启动失败" }
