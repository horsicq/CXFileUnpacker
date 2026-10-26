param([Parameter(Mandatory = $true)][string]$Executable)

$ErrorActionPreference = 'Stop'
$resolvedExecutable = (Resolve-Path -LiteralPath $Executable).Path
$tracePath = Join-Path ([System.IO.Path]::GetDirectoryName($resolvedExecutable)) `
    ('encryption-smoke-' + [System.IO.Path]::GetFileNameWithoutExtension($resolvedExecutable) + '.log')
if (Test-Path -LiteralPath $tracePath) { Clear-Content -LiteralPath $tracePath }
$env:XFU_ENCRYPTION_SMOKE_LOG = $tracePath
# A separate hidden console preserves real console handles for the TUI's
# modal-dialog checks. Redirecting stdout would replace its screen buffer.
$smokeProcess = Start-Process -FilePath $resolvedExecutable `
    -ArgumentList '--smoke-encryption' -WindowStyle Hidden -PassThru `
    -WorkingDirectory ([System.IO.Path]::GetDirectoryName($resolvedExecutable))
if (-not $smokeProcess.WaitForExit(20000)) {
    $smokeProcess.Kill()
    $smokeProcess.WaitForExit()
    Get-Content -LiteralPath $tracePath -Tail 50 -ErrorAction SilentlyContinue
    Write-Error 'Encryption UI smoke timed out.'
    exit 2
}
$smokeProcess.Refresh()
Get-Content -LiteralPath $tracePath -Tail 50 -ErrorAction SilentlyContinue
Write-Output ('Encryption UI smoke exit code: ' + $smokeProcess.ExitCode)
exit $smokeProcess.ExitCode
