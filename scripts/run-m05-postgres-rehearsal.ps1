$ErrorActionPreference = "Stop"

$project = "rag-tool-m05-rehearsal"
$compose = Join-Path $PSScriptRoot "..\docker-compose.rehearsal.yml"
$exitCode = 1

& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop is not running. Start it and retry."
}

try {
    & docker compose --project-name $project --file $compose up `
        --detach `
        --wait `
        db
    if ($LASTEXITCODE -ne 0) {
        throw "The rehearsal database did not become healthy."
    }

    & docker compose --project-name $project --file $compose run --rm migrate
    if ($LASTEXITCODE -ne 0) {
        throw "The migration rehearsal failed."
    }

    & docker compose --project-name $project --file $compose run `
        --rm `
        --build `
        --no-deps `
        rehearsal
    $exitCode = $LASTEXITCODE
}
finally {
    & docker compose --project-name $project --file $compose down `
        --volumes `
        --remove-orphans
    $cleanupExitCode = $LASTEXITCODE
    if ($cleanupExitCode -ne 0 -and $exitCode -eq 0) {
        $exitCode = $cleanupExitCode
    }
}

exit $exitCode
