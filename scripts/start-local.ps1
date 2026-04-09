$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$frontendDir = Join-Path $repoRoot "frontend"
$apiBase = "http://localhost:8000"
$frontendPort = 3000

function Test-DockerReady {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        docker version > $null 2>&1
        return ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Ensure-DockerReady {
    if (Test-DockerReady) {
        return
    }

    $dockerDesktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path $dockerDesktop)) {
        throw "Docker Desktop is not running and was not found at '$dockerDesktop'."
    }

    Write-Host "Docker Desktop is not running. Starting it..." -ForegroundColor Yellow
    Start-Process $dockerDesktop | Out-Null

    $deadline = (Get-Date).AddMinutes(3)
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerReady) {
            return
        }
        Start-Sleep -Seconds 3
    }

    throw "Docker Desktop did not become ready in time."
}

function Wait-ForBackend {
    param(
        [string]$HealthUrl,
        [int]$TimeoutSeconds = 90
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing $HealthUrl -TimeoutSec 5
            if ($response.Content -match '"ok"\s*:\s*true') {
                return $true
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    }

    return $false
}

Write-Host "[1/3] Starting db, redis, and backend via Docker..." -ForegroundColor Cyan
Ensure-DockerReady
Push-Location $repoRoot
try {
    docker compose up -d --build db redis backend
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose up failed."
    }
} finally {
    Pop-Location
}

Write-Host "[2/3] Waiting for backend health..." -ForegroundColor Cyan
if (-not (Wait-ForBackend -HealthUrl "$apiBase/health")) {
    throw "Backend did not become healthy at $apiBase/health. Check: docker compose logs --tail=80 backend"
}

if (-not (Test-Path (Join-Path $frontendDir "node_modules\next\package.json"))) {
    Write-Host "[3/3] Installing frontend dependencies..." -ForegroundColor Cyan
    Push-Location $frontendDir
    try {
        npm install --fetch-timeout=600000 --fetch-retries=10 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000
    } finally {
        Pop-Location
    }
} else {
    Write-Host "[3/3] Frontend dependencies already present." -ForegroundColor Cyan
}

$frontendCommand = @(
    "Set-Location '$frontendDir'"
    "`$env:NEXT_PUBLIC_API_BASE='$apiBase'"
    "npm run dev"
) -join "; "

Write-Host "Launching frontend dev server in a new PowerShell window..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @("-NoExit", "-Command", $frontendCommand) -WorkingDirectory $frontendDir

Write-Host ""
Write-Host "Local stack is starting." -ForegroundColor Green
Write-Host "Backend:  $apiBase"
Write-Host "Frontend: http://127.0.0.1:$frontendPort"
Write-Host ""
Write-Host "Useful commands:"
Write-Host "  docker compose ps"
Write-Host "  docker compose logs --tail=80 backend"
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts/check-local.ps1"
