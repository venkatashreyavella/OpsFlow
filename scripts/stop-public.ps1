$ErrorActionPreference = 'Stop'
$opsflowRoot = Split-Path -Parent $PSScriptRoot
$opsflowStateFile = Join-Path $opsflowRoot '.local/public-share.json'
if (-not (Test-Path -LiteralPath $opsflowStateFile)) { Write-Output 'There is no tracked public share.'; return }
$opsflowState = Get-Content -Raw -LiteralPath $opsflowStateFile | ConvertFrom-Json
$opsflowProcesses = @(
    @{ pid = $opsflowState.tunnel_pid; expected = (Join-Path $opsflowRoot '.local/tools/cloudflared.exe') },
    @{ pid = $opsflowState.api_pid; expected = (Join-Path $opsflowRoot '.venv/Scripts/python.exe') }
)
foreach ($opsflowProcess in $opsflowProcesses) {
    $opsflowActual = Get-CimInstance Win32_Process -Filter "ProcessId=$($opsflowProcess.pid)"
    if ($null -eq $opsflowActual) { continue }
    $opsflowExpected = $opsflowProcess.expected.Replace('/', '\')
    if ($opsflowActual.CommandLine.Replace('/', '\').IndexOf($opsflowExpected, [StringComparison]::OrdinalIgnoreCase) -lt 0) { throw 'The tracked process no longer matches this project. Stop was cancelled.' }
    if ($opsflowProcess.pid -eq $opsflowState.api_pid -and $opsflowActual.CommandLine -notmatch 'app\.main:app.*--port\s+8002') { throw 'The tracked Python process is not the public app server.' }
    & taskkill.exe /PID $opsflowProcess.pid /T /F | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not stop a public-sharing process.' }
}
Remove-Item -LiteralPath $opsflowStateFile
Write-Output 'Public sharing stopped.'
