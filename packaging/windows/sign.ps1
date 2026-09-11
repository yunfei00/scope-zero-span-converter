param([Parameter(Mandatory=$true)][string]$Path)
$ErrorActionPreference = 'Stop'
if (-not $env:WINDOWS_CERTIFICATE_BASE64 -and -not $env:WINDOWS_CERTIFICATE_PASSWORD) {
    Write-Host "UNSIGNED BUILD: no signing certificate configured ($Path)"
    if ($env:GITHUB_STEP_SUMMARY) { "UNSIGNED BUILD: $Path" >> $env:GITHUB_STEP_SUMMARY }
    exit 0
}
if (-not $env:WINDOWS_CERTIFICATE_BASE64 -or -not $env:WINDOWS_CERTIFICATE_PASSWORD) {
    throw 'Signing secrets are only partially configured'
}
$signTool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" | Sort-Object FullName -Descending | Select-Object -First 1
if (-not $signTool) { throw 'Windows SDK signtool was not found' }
$pfxPath = Join-Path $env:RUNNER_TEMP ('scope-signing-' + [guid]::NewGuid() + '.pfx')
try {
    [IO.File]::WriteAllBytes($pfxPath, [Convert]::FromBase64String($env:WINDOWS_CERTIFICATE_BASE64))
    & $signTool.FullName sign /f $pfxPath /p $env:WINDOWS_CERTIFICATE_PASSWORD /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $Path
    if ($LASTEXITCODE -ne 0) { throw 'Signing failed' }
    & $signTool.FullName verify /pa $Path
    if ($LASTEXITCODE -ne 0) { throw 'Signature verification failed' }
    Write-Host "SIGNED BUILD: $Path"
} finally {
    # Only this invocation's temporary PFX; never placed in an artifact directory.
    if (Test-Path -LiteralPath $pfxPath) { Remove-Item -LiteralPath $pfxPath -Force }
}
