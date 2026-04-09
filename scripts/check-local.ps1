$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

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

function Test-Endpoint {
    param(
        [string]$Name,
        [string]$Url
    )

    try {
        $response = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 5
        Write-Host ("[OK] {0}: {1}" -f $Name, $response.StatusCode) -ForegroundColor Green
        return $true
    } catch {
        Write-Host ("[FAIL] {0}: {1}" -f $Name, $_.Exception.Message) -ForegroundColor Yellow
        return $false
    }
}

if (Test-DockerReady) {
    Push-Location $repoRoot
    try {
        Write-Host "Docker services:" -ForegroundColor Cyan
        docker compose ps
    } finally {
        Pop-Location
    }
} else {
    Write-Host "[WARN] Docker Desktop is not running." -ForegroundColor Yellow
}

Write-Host ""
Test-Endpoint -Name "Backend health" -Url "http://127.0.0.1:8000/health" | Out-Null
Test-Endpoint -Name "Frontend" -Url "http://127.0.0.1:3000" | Out-Null
