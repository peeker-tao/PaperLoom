<#
.SYNOPSIS
  Build the PaperLoom plugin XPI and the Windows service package.

.DESCRIPTION
  Requires Node.js (npm) and Python. It typechecks, builds the esbuild bundles,
  copies the runtime files into plugin/, and produces:
    dist/paperloom-<version>.xpi
    dist/paperloom-service-<version>.zip
    dist/updates.json
#>
[CmdletBinding()]
param(
  [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
  if (-not $Python) {
    $candidates = @(
      (Join-Path $root ".venv\Scripts\python.exe"),
      (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
    )
    $Python = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
  }
  if (-not $Python) {
    throw "Python not found. Pass -Python <path-to-python.exe>."
  }

  Write-Host "==> typecheck" -ForegroundColor Cyan
  Push-Location plugin
  try {
    node node_modules/typescript/bin/tsc --noEmit
    if ($LASTEXITCODE -ne 0) { throw "typecheck failed" }
    Write-Host "==> build bundles" -ForegroundColor Cyan
    node esbuild.config.mjs
    if ($LASTEXITCODE -ne 0) { throw "esbuild failed" }
  }
  finally {
    Pop-Location
  }

  Write-Host "==> icons" -ForegroundColor Cyan
  & $Python scripts/gen_icons.py
  if ($LASTEXITCODE -ne 0) { throw "icon generation failed" }

  Write-Host "==> package" -ForegroundColor Cyan
  & $Python scripts/pack.py
  if ($LASTEXITCODE -ne 0) { throw "packaging failed" }

  Write-Host "Done. Artifacts in dist/" -ForegroundColor Green
}
finally {
  Pop-Location
}
