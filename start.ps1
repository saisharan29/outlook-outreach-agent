# One-click start on Windows: installs what is missing, checks the setup, starts the chat, opens the browser.
#   Right-click > Run with PowerShell, or in a terminal:  .\start.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Host "Python is not installed. Install Python 3.11 or 3.12 from https://www.python.org/downloads/ (tick 'Add python.exe to PATH')." -ForegroundColor Red
  exit 1
}
if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host ".env created from .env.example. Open it in Notepad, fill MS_CLIENT_ID, MS_CLIENT_SECRET, APP_PASSWORD, SECRET_KEY (and ANTHROPIC_API_KEY), then run start.ps1 again." -ForegroundColor Yellow
  notepad .env
  exit 0
}
if ((Test-Path ".git") -and ($env:AUTO_UPDATE -ne "0") -and (Get-Command git -ErrorAction SilentlyContinue)) {
  Write-Host "== Checking for updates" -ForegroundColor Cyan
  git pull --ff-only
}
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if (-not (Test-Path "Agency\Templates")) {
  Write-Host "No Agency folder next to the code: writing the sample one (templates, example files)." -ForegroundColor Yellow
  python -m outreach.cli demo
}
Write-Host "`n== Status ==" -ForegroundColor Cyan
python -m outreach.cli status
$port = if ($env:PORT) { $env:PORT } else { "8080" }
Write-Host "`nStarting the chat on http://localhost:$port  (Ctrl+C stops it)" -ForegroundColor Green
Start-Process "http://localhost:$port"
python -m outreach.cli serve
