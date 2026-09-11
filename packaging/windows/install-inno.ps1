$ErrorActionPreference = 'Stop'
$installer = Join-Path $env:RUNNER_TEMP 'innosetup-6.4.3.exe'
$compilerDirectory = Join-Path $env:RUNNER_TEMP 'inno-setup-6.4.3'
Invoke-WebRequest 'https://github.com/jrsoftware/issrc/releases/download/is-6_4_3/innosetup-6.4.3.exe' -OutFile $installer
if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash -ne 'F3C42116542C4CC57263C5BA6C4FEABFC49FE771F2F98A79D2F7628B8762723B') {
    throw 'Inno Setup installer checksum mismatch'
}
$process = Start-Process -FilePath $installer -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/CURRENTUSER', '/NOICONS', "/DIR=`"$compilerDirectory`"") -WindowStyle Hidden -Wait -PassThru
if ($process.ExitCode -ne 0) { throw 'Inno Setup installation failed' }
$compiler = Join-Path $compilerDirectory 'ISCC.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw 'Inno compiler is missing' }
if ($env:GITHUB_ENV) { "INNO_COMPILER=$compiler" >> $env:GITHUB_ENV }
Write-Output $compiler
