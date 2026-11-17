<#
.SYNOPSIS
  Install the PaperLoom Python service into a virtual environment.

.DESCRIPTION
  Creates .venv next to this repository (if missing) and installs the service
  package in editable mode. Safe to re-run.
#>
[CmdletBinding()]
param(
  [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".venv"
$target = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $target)) {
  Write-Host "==> creating venv at $venv" -ForegroundColor Cyan
  & $Python -m venv $venv
  if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
}

Write-Host "==> installing service" -ForegroundColor Cyan
& $target -m pip install --upgrade pip --quiet
& $target -m pip install -e (Join-Path $root "service") --no-build-isolation
if ($LASTEXITCODE -ne 0) { throw "service installation failed" }

Write-Host "==> checking" -ForegroundColor Cyan
& $target -m paperloom_service --check
