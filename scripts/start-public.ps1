$ErrorActionPreference = 'Stop'
$opsflowRoot = Split-Path -Parent $PSScriptRoot
$opsflowLocal = Join-Path $opsflowRoot '.local'
$opsflowPython = Join-Path $opsflowRoot '.venv/Scripts/python.exe'
$opsflowTunnelExe = Join-Path $opsflowLocal 'tools/cloudflared.exe'
$opsflowStateFile = Join-Path $opsflowLocal 'public-share.json'
$opsflowTunnelLog = Join-Path $opsflowLocal 'public-tunnel.stderr.log'
$opsflowApiProcess = $null
$opsflowTunnelProcess = $null

if (-not (Test-Path -LiteralPath $opsflowPython)) { throw 'Set up the project virtual environment first.' }
if (-not (Test-Path -LiteralPath $opsflowTunnelExe)) { throw 'Cloudflare cloudflared.exe must be available in .local/tools.' }

if (Test-Path -LiteralPath $opsflowStateFile) {
    $opsflowExisting = Get-Content -Raw -LiteralPath $opsflowStateFile | ConvertFrom-Json
    $opsflowExistingTunnel = Get-Process -Id $opsflowExisting.tunnel_pid -ErrorAction SilentlyContinue
    $opsflowExistingApi = Get-Process -Id $opsflowExisting.api_pid -ErrorAction SilentlyContinue
    if ($opsflowExistingTunnel -and $opsflowExistingApi) {
        Write-Output $opsflowExisting.public_url
        return
    }
    throw 'A previous share has stopped. Run scripts/stop-public.ps1 before starting a new link.'
}

if (Get-NetTCPConnection -LocalPort 8002 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8002 is already in use. Stop the existing public share before continuing.'
}

try {
    $opsflowPreviousSecure = $env:OPSFLOW_COOKIE_SECURE
    try {
        $env:OPSFLOW_COOKIE_SECURE = 'true'
        $opsflowApiProcess = Start-Process -FilePath $opsflowPython -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8002' -WorkingDirectory $opsflowRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $opsflowLocal 'public-api.stdout.log') -RedirectStandardError (Join-Path $opsflowLocal 'public-api.stderr.log')
    } finally {
        $env:OPSFLOW_COOKIE_SECURE = $opsflowPreviousSecure
    }

    $opsflowReady = $false
    for ($opsflowAttempt = 0; $opsflowAttempt -lt 30; $opsflowAttempt++) {
        Start-Sleep -Milliseconds 500
        $opsflowApiProcess.Refresh()
        if ($opsflowApiProcess.HasExited) { throw 'The public app server exited. Check .local/public-api.stderr.log.' }
        try {
            $opsflowStatus = Invoke-RestMethod -Uri 'http://127.0.0.1:8002/auth/status' -TimeoutSec 2
            $opsflowReady = $true
            break
        } catch { continue }
    }
    if (-not $opsflowReady) { throw 'The app server did not become ready.' }
    if ($opsflowStatus.setup_required) { throw 'Create your administrator account locally before sharing the app publicly.' }

    $opsflowTunnelProcess = Start-Process -FilePath $opsflowTunnelExe -ArgumentList 'tunnel','--url','http://127.0.0.1:8002','--no-autoupdate' -WorkingDirectory $opsflowRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $opsflowLocal 'public-tunnel.stdout.log') -RedirectStandardError $opsflowTunnelLog
    $opsflowPublicUrl = $null
    for ($opsflowAttempt = 0; $opsflowAttempt -lt 90; $opsflowAttempt++) {
        Start-Sleep -Milliseconds 500
        $opsflowTunnelProcess.Refresh()
        if ($opsflowTunnelProcess.HasExited) { throw 'Cloudflare exited. Check .local/public-tunnel.stderr.log.' }
        if (Test-Path -LiteralPath $opsflowTunnelLog) {
            $opsflowMatch = [regex]::Match((Get-Content -Raw -LiteralPath $opsflowTunnelLog), 'https://[a-z0-9-]+\.trycloudflare\.com')
            if ($opsflowMatch.Success) { $opsflowPublicUrl = $opsflowMatch.Value; break }
        }
    }
    if (-not $opsflowPublicUrl) { throw 'Cloudflare did not return a public URL in time.' }
    @{
        public_url = $opsflowPublicUrl
        api_pid = $opsflowApiProcess.Id
        tunnel_pid = $opsflowTunnelProcess.Id
        started_at = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    } | ConvertTo-Json | Set-Content -LiteralPath $opsflowStateFile
    Write-Output $opsflowPublicUrl
} catch {
    if ($opsflowTunnelProcess -and -not $opsflowTunnelProcess.HasExited) { & taskkill.exe /PID $opsflowTunnelProcess.Id /T /F | Out-Null }
    if ($opsflowApiProcess -and -not $opsflowApiProcess.HasExited) { & taskkill.exe /PID $opsflowApiProcess.Id /T /F | Out-Null }
    throw
}
