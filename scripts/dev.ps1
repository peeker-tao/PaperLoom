<#
.SYNOPSIS
  Start the local service and rebuild the plugin on change.
#>
[CmdletBinding()]
param(
  [int]$Port = 23124,
  [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
  if (-not $Python) {
    $Python = Join-Path $root ".venv\Scripts\python.exe"
    if (-not (Test-Path $Python)) { $Python = "python" }
  }

  $service = Start-Process -FilePath $Python `
    -ArgumentList "-m", "paperloom_service", "--port", "$Port", "--data-dir", (Join-Path $root "data") `
    -WorkingDirectory $root -PassThru -WindowStyle Hidden
  Write-Host "service pid $($service.Id) on http://127.0.0.1:$Port" -ForegroundColor Cyan

  Push-Location plugin
  try {
    npm.cmd run watch
  }
  finally {
    Pop-Location
    Stop-Process -Id $service.Id -ErrorAction SilentlyContinue
  }
}
finally {
  Pop-Location
}
