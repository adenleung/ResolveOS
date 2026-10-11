param([switch]$Offline, [ValidateSet('A','B','C')][string]$Scenario = 'A')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $testPython = Join-Path $PSScriptRoot '.tools/live-ai-venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $testPython)) {
        & py -3.13 -m venv (Join-Path $PSScriptRoot '.tools/live-ai-venv')
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 is required; virtual environment setup failed.' }
        & $testPython -m pip install -r requirements.txt -c requirements-hardening-constraints.txt
        if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
    }
    & $testPython -c "import sqlalchemy, alembic, psycopg, pydantic_settings"
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependencies unavailable. Remove the incomplete .tools/live-ai-venv and retry.' }
    if ($Offline) { & $testPython run_live_ai_test.py --scenario $Scenario }
    else { & $testPython run_live_ai_test.py --live --scenario $Scenario }
    $testExitCode = $LASTEXITCODE
} finally { Pop-Location }
exit $testExitCode
