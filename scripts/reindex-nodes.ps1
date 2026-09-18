param(
    [Parameter(Mandatory = $true)]
    [int]$DatasetId,

    [string]$ApiBase = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"

$endpoint = "$ApiBase/datasets/$DatasetId/reindex-nodes"
Write-Host ("Reindexing knowledge nodes for dataset #{0} via {1}" -f $DatasetId, $endpoint) -ForegroundColor Cyan

try {
    $response = Invoke-RestMethod -Method Post -Uri $endpoint -TimeoutSec 600
    $response | ConvertTo-Json -Depth 8
} catch {
    Write-Host ("Reindex failed: {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}
