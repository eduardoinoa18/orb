param(
    [int]$PreferredPort = 8000,
    [string]$BindHost = "127.0.0.1",
    [switch]$Reload,
    [switch]$ProbeOnly,
    [switch]$EnforcePreflight
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-PortAvailable {
    param(
        [int]$Port,
        [string]$BindAddress
    )

    $listener = $null
    try {
        $ip = [System.Net.IPAddress]::Any
        if ($BindAddress -eq "127.0.0.1" -or $BindAddress -eq "localhost") {
            $ip = [System.Net.IPAddress]::Loopback
        }
        $listener = [System.Net.Sockets.TcpListener]::new($ip, $Port)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($listener) {
            $listener.Stop()
        }
    }
}

function Get-FreePort {
    param(
        [int]$StartPort,
        [string]$BindAddress
    )

    for ($port = $StartPort; $port -lt ($StartPort + 100); $port++) {
        if (Test-PortAvailable -Port $port -BindAddress $BindAddress) {
            return $port
        }
    }

    throw "Could not find a free port between $StartPort and $($StartPort + 99)."
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found at $pythonExe. Create the venv first."
}

$port = Get-FreePort -StartPort $PreferredPort -BindAddress $BindHost
$url = "http://${BindHost}:${port}"
$preflightScript = Join-Path $projectRoot "scripts\preflight_check.py"

if (-not (Test-Path $preflightScript)) {
    throw "Preflight script not found at $preflightScript"
}

if ($ProbeOnly) {
    Write-Output "ORB API probe: free port found at $url"
    exit 0
}

Write-Output "Running full platform preflight..."
$preflightArgs = @($preflightScript)
if ($EnforcePreflight) {
    $preflightArgs += "--strict"
}
$preflightOutput = & $pythonExe @preflightArgs 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Preflight check failed. Resolve blockers before startup."
    $preflightOutput | ForEach-Object { Write-Output $_ }
    if ($EnforcePreflight) {
        throw "Preflight enforcement enabled and full preflight failed. Refusing to start API."
    }
} else {
    Write-Output "Preflight check passed."
    $preflightOutput | ForEach-Object { Write-Output $_ }
}

Write-Output "Starting ORB API at $url"
Write-Output "Press Ctrl+C to stop."

Push-Location $projectRoot
try {
    $uvicornArgs = @("-m", "uvicorn", "app.api.main:app", "--host", $BindHost, "--port", "$port")
    if ($Reload) {
        $uvicornArgs += "--reload"
    }

    & $pythonExe @uvicornArgs
} finally {
    Pop-Location
}
