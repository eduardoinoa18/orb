param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$AgentId = "",
    [string]$StrategyName = "ORB Level 8 Momentum",
    [string]$SourceTrader = "orb-smoke-script"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-OrbJson {
    param(
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][string]$Url,
        [object]$Body
    )

    $jsonBody = $null
    if ($null -ne $Body) {
        $jsonBody = $Body | ConvertTo-Json -Depth 8
    }

    try {
        if ($null -eq $jsonBody) {
            return Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json"
        }
        return Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body $jsonBody
    }
    catch {
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
            throw "Request failed ($Method $Url): $($_.ErrorDetails.Message)"
        }
        throw "Request failed ($Method $Url): $($_.Exception.Message)"
    }
}

function Test-IsUuid {
    param([string]$Value)
    return [bool]($Value -match '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$')
}

function Resolve-AgentId {
    param(
        [string]$BaseUrl,
        [string]$RequestedAgentId
    )

    if ($RequestedAgentId -and (Test-IsUuid -Value $RequestedAgentId)) {
        return $RequestedAgentId
    }

    $dashboard = Invoke-OrbJson -Method "GET" -Url "$BaseUrl/dashboard/data"
    $agents = @()
    if ($dashboard -and $dashboard.agents) {
        $agents = @($dashboard.agents)
    }

    foreach ($agent in $agents) {
        $candidate = [string]$agent.id
        if (Test-IsUuid -Value $candidate) {
            return $candidate
        }
    }

    throw "No valid agent UUID found. Provide -AgentId with an existing agents.id value."
}

$resolvedAgentId = Resolve-AgentId -BaseUrl $BaseUrl -RequestedAgentId $AgentId

Write-Host "[1/5] Checking health..."
$health = Invoke-OrbJson -Method "GET" -Url "$BaseUrl/health"
if ($health.status -ne "healthy") {
    throw "Health check failed. Response: $($health | ConvertTo-Json -Depth 6)"
}

Write-Host "[2/5] Ingesting strategy..."
$ingestPayload = @{
    agent_id = $resolvedAgentId
    strategy_name = $StrategyName
    notes = "Long only breakout pullback setup during the opening hour. One to two trades max, stop after two losses, and preserve capital first."
    source_trader = $SourceTrader
}
$ingest = Invoke-OrbJson -Method "POST" -Url "$BaseUrl/agents/orion/ingest" -Body $ingestPayload
if ($ingest.status -ne "ingested") {
    throw "Ingest step failed. Response: $($ingest | ConvertTo-Json -Depth 8)"
}

Write-Host "[3/5] Running market scan..."
$scanPayload = @{
    agent_id = $resolvedAgentId
    symbols = @("ES", "NQ")
    timeframe = "5m"
}
$scan = Invoke-OrbJson -Method "POST" -Url "$BaseUrl/agents/orion/scan" -Body $scanPayload
if (-not $scan.status) {
    throw "Scan step failed. Response: $($scan | ConvertTo-Json -Depth 8)"
}

$setups = @()
if ($scan.setups) {
    $setups = @($scan.setups)
}

$selectedSetup = $null
if ($setups.Count -gt 0) {
    $selectedSetup = $setups[0]
}

if ($null -eq $selectedSetup) {
    Write-Host "No scan setup found. Using deterministic fallback paper-trade setup."
    $selectedSetup = @{
        instrument = "ES"
        direction = "long"
        entry_price = 5320.0
        stop_loss = 5318.5
        take_profit = 5323.0
    }
}

Write-Host "[4/5] Running paper-trade test..."
$paperPayload = @{
    agent_id = $resolvedAgentId
    instrument = [string]$selectedSetup.instrument
    direction = [string]$selectedSetup.direction
    entry_price = [double]$selectedSetup.entry_price
    stop_loss = [double]$selectedSetup.stop_loss
    take_profit = [double]$selectedSetup.take_profit
    account_balance = 50000
    risk_percent = 1.0
}
$paper = Invoke-OrbJson -Method "POST" -Url "$BaseUrl/agents/orion/paper-trade/test" -Body $paperPayload
if ($paper.status -notin @("opened", "blocked", "rejected")) {
    throw "Paper-trade step returned unexpected status. Response: $($paper | ConvertTo-Json -Depth 8)"
}

Write-Host "[5/5] Pulling performance summary..."
$perf = Invoke-OrbJson -Method "GET" -Url "$BaseUrl/agents/orion/performance?agent_id=$resolvedAgentId&days=14"

$result = [ordered]@{
    success = $true
    agent_id = $resolvedAgentId
    health = $health
    ingest_status = $ingest.status
    scan_status = $scan.status
    setup_count = $setups.Count
    paper_status = $paper.status
    live_trades = $perf.live_trades
    paper_trades = $perf.paper_trades
    recommendations = $perf.recommendations
}

Write-Host "Orion Level 8 smoke run complete:"
$result | ConvertTo-Json -Depth 8
