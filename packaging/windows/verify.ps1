param([Parameter(Mandatory=$true)][ValidateSet('exe','installer')][string]$Stage)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$metadata = Get-Content (Join-Path $repo 'build/packaging/metadata.json') -Raw | ConvertFrom-Json
$results = Join-Path $repo 'build/verification'
New-Item -ItemType Directory -Force -Path $results | Out-Null
$env:QT_QPA_PLATFORM = 'offscreen'
$env:SCOPE_ZERO_SPAN_DATA_DIR = Join-Path $results 'user-data'
New-Item -ItemType Directory -Force -Path $env:SCOPE_ZERO_SPAN_DATA_DIR | Out-Null

function Invoke-Checked([string]$File, [string[]]$Arguments) {
    # -Wait includes Inno's child setup process and windowed applications.
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -Wait -PassThru -WindowStyle Hidden
    if ($process.ExitCode -ne 0) { throw "$File exited with $($process.ExitCode)" }
}

function Test-App([string]$Exe, [string]$ReportName) {
    if (-not (Test-Path -LiteralPath $Exe)) { throw "Missing EXE: $Exe" }
    $version = (Get-Item -LiteralPath $Exe).VersionInfo
    if ($version.ProductVersion -ne $metadata.version -or $version.FileVersion -ne $metadata.version) { throw 'EXE version does not match source' }
    if ($version.ProductName -ne $metadata.product_name -or $version.CompanyName -ne $metadata.publisher) { throw 'EXE product identity mismatch' }
    $reportPath = Join-Path $results "$ReportName.json"
    if (Test-Path -LiteralPath $reportPath) { Remove-Item -LiteralPath $reportPath }
    Invoke-Checked $Exe @('--smoke-test', '--smoke-report', "`"$reportPath`"")
    $report = Get-Content $reportPath -Raw | ConvertFrom-Json
    if ($report.status -ne 'PASS' -or -not $report.frozen -or $report.version -ne $metadata.version) { throw "Packaged smoke failed: $reportPath" }
    if ($report.executable -ne (Resolve-Path -LiteralPath $Exe).Path) { throw 'Smoke ran the wrong executable' }
    if ($report.tabs.Count -ne 5) { throw 'Expected five tabs' }
    Write-Host "$ReportName PASS: $Exe"
}

if ($Stage -eq 'exe') {
    Test-App (Join-Path $repo "dist/$($metadata.application_id)/$($metadata.executable)") 'packaged-exe'
    exit 0
}

$setup = Join-Path $repo "dist/artifacts/$($metadata.installer_filename)"
if ((Get-Item -LiteralPath $setup).Length -le 0) { throw 'Empty installer' }
$installation = Join-Path $env:RUNNER_TEMP ('scope-installer-smoke-' + [guid]::NewGuid())
$sentinel = Join-Path $env:SCOPE_ZERO_SPAN_DATA_DIR 'customer-data-sentinel.txt'
'preserve customer data' | Set-Content $sentinel
$arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', "/DIR=`"$installation`"", '/TASKS=desktopicon')
Invoke-Checked $setup $arguments
$installedExe = Join-Path $installation $metadata.executable
Test-App $installedExe 'installed-exe'
# Reinstall: verify stable AppId registration does not create another product.
Invoke-Checked $setup $arguments
$registry = Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' | Where-Object { $_.PSChildName -eq "$($metadata.app_id)_is1" }
if (@($registry).Count -ne 1 -or $registry.DisplayVersion -ne $metadata.version) { throw 'Installer upgrade registration mismatch' }
$startShortcut = Join-Path ([Environment]::GetFolderPath('CommonPrograms')) "$($metadata.product_name).lnk"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) "$($metadata.product_name).lnk"
foreach ($shortcut in @($startShortcut, $desktopShortcut)) {
    if (-not (Test-Path -LiteralPath $shortcut)) { throw "Shortcut missing: $shortcut" }
    $target = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcut).TargetPath
    if ($target -ne $installedExe) { throw 'Shortcut points at the wrong EXE' }
}
Invoke-Checked (Join-Path $installation 'unins000.exe') @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
if (Test-Path -LiteralPath $installation) { throw "Uninstall left the installation directory: $installation" }
foreach ($shortcut in @($startShortcut, $desktopShortcut)) {
    if (Test-Path -LiteralPath $shortcut) { throw 'Uninstall left a shortcut' }
}
if ((Get-Content $sentinel -Raw).Trim() -ne 'preserve customer data') { throw 'Uninstall removed user data' }
@{ installer='PASS'; silent_install='PASS'; installed_smoke='PASS'; upgrade_registration='PASS'; shortcuts='PASS'; silent_uninstall='PASS'; user_data_preserved='PASS' } | ConvertTo-Json | Set-Content (Join-Path $results 'installer.json')
Write-Host 'Installer / installed EXE / upgrade registration / uninstall / user-data preservation PASS'
