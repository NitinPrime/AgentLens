# Start AgentLens locally on Windows without Docker.
# Usage (from the repo root):  .\scripts\dev.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host "AgentLens local development (no Docker required)"
Write-Host ""

# First run gets a working .env: SQLite instead of Postgres, an in-process token
# store instead of Redis, and a real JWT secret rather than the insecure default.
$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "No .env found. Creating one for local development..."
    $secret = python -c "import secrets; print(secrets.token_hex(32))"
    Get-Content (Join-Path $Root ".env.example") |
        ForEach-Object {
            $_ -replace '^DATABASE_URL=.*', 'DATABASE_URL=sqlite+aiosqlite:///./agentlens.db' `
               -replace '^REDIS_URL=.*', 'REDIS_URL=memory://' `
               -replace '^JWT_SECRET_KEY=.*', "JWT_SECRET_KEY=$secret"
        } |
        Set-Content $envFile
    Write-Host "  Wrote .env using SQLite and an in-process token store."
}

$apiVenvPython = Join-Path $Root "apps\api\.venv\Scripts\python.exe"
if (-not (Test-Path $apiVenvPython)) {
    Write-Host "Creating Python virtualenv..."
    python -m venv (Join-Path $Root "apps\api\.venv")
}

Write-Host "Installing backend dependencies..."
& $apiVenvPython -m pip install -q -r (Join-Path $Root "apps\api\requirements.txt")

$webDir = Join-Path $Root "apps\web"
if (-not (Test-Path (Join-Path $webDir "node_modules"))) {
    Write-Host "Installing frontend dependencies..."
    Push-Location $webDir
    npm install
    Pop-Location
}

$apiCmd = "Set-Location '$Root\apps\api'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
$webCmd = "Set-Location '$Root\apps\web'; npm run dev"

Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCmd
Start-Process powershell -ArgumentList "-NoExit", "-Command", $webCmd

Write-Host "Opened two terminals for the API and the web app."

# Wait for the API before returning, so `seed_demo.py` can be run on the next
# line of a script without racing the server's startup.
Write-Host -NoNewline "Waiting for the API"
$ready = $false
foreach ($attempt in 1..40) {
    try {
        Invoke-RestMethod "http://127.0.0.1:8000/health" -TimeoutSec 2 | Out-Null
        $ready = $true
        break
    }
    catch {
        Write-Host -NoNewline "."
        Start-Sleep -Milliseconds 500
    }
}
Write-Host ""

if ($ready) {
    Write-Host "API   : http://localhost:8000/docs"
    Write-Host "Web   : http://localhost:3000"
    Write-Host ""
    Write-Host "Seed a demo workspace with realistic data:"
    Write-Host "  .\apps\api\.venv\Scripts\python.exe scripts\seed_demo.py"
}
else {
    Write-Warning "The API did not answer on port 8000. Check the API terminal for the error."
}
