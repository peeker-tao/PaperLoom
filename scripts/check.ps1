<#
.SYNOPSIS
  Run all checks: TypeScript, service tests, plugin build, secret scan.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
  $python = Join-Path $root ".venv\Scripts\python.exe"
  if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
  }

  Write-Host "==> TypeScript" -ForegroundColor Cyan
  Push-Location plugin
  try {
    node node_modules/typescript/bin/tsc --noEmit
    if ($LASTEXITCODE -ne 0) { throw "typecheck failed" }
    node test/overlay.test.mjs
    if ($LASTEXITCODE -ne 0) { throw "plugin unit tests failed" }
    node test/jump.test.mjs
    if ($LASTEXITCODE -ne 0) { throw "plugin jump tests failed" }
    node test/model.test.mjs
    if ($LASTEXITCODE -ne 0) { throw "plugin model tests failed" }
    node test/pages.test.mjs
    if ($LASTEXITCODE -ne 0) { throw "plugin page tests failed" }
    node test/composer.test.mjs
    if ($LASTEXITCODE -ne 0) { throw "plugin composer tests failed" }
    node test/attachments.test.mjs
    if ($LASTEXITCODE -ne 0) { throw "plugin attachment tests failed" }
    node esbuild.config.mjs
    if ($LASTEXITCODE -ne 0) { throw "build failed" }
  }
  finally {
    Pop-Location
  }

  Write-Host "==> service lint" -ForegroundColor Cyan
  & $python -m ruff check service scripts
  if ($LASTEXITCODE -ne 0) { throw "lint failed" }

  Write-Host "==> service tests" -ForegroundColor Cyan
  & $python -m pytest service/tests -q
  if ($LASTEXITCODE -ne 0) { throw "tests failed" }

  Write-Host "==> secret scan" -ForegroundColor Cyan
  $patterns = 'sk-[A-Za-z0-9]{16,}|DEEPSEEK_API_KEY\s*=\s*["'']?[A-Za-z0-9]'
  $hits = git grep -InE $patterns -- . ':!plugin/node_modules' ':!docs' 2>$null
  if ($hits) {
    Write-Host $hits -ForegroundColor Red
    throw "potential secret found in tracked files"
  }
  Write-Host "no secrets found" -ForegroundColor Green
  Write-Host "All checks passed." -ForegroundColor Green
}
finally {
  Pop-Location
}
