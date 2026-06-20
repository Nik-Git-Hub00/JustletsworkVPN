$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$VenvPython = Join-Path "venv" "Scripts/python.exe"
$Version = if ($env:APP_VERSION) { $env:APP_VERSION } else { (Get-Content "VERSION" -First 1).Trim() }

if (-not (Test-Path $VenvPython)) {
    & $Python -c "import sys; sys.exit('Python 3.11+ is required') if sys.version_info < (3, 11) else None"
    & $Python -m venv venv
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements.txt

if (-not (Test-Path "runtime/windows-amd64/sing-box.exe") -or -not (Test-Path "runtime/windows-amd64/libcronet.dll")) {
    ./scripts/fetch_runtime_windows.ps1 -Arch amd64
}

& $VenvPython -m PyInstaller --clean -y specs/windows.spec

$ReleaseDir = "release"
$StageDir = Join-Path $ReleaseDir "WorkVPN-windows-amd64"
$ZipPath = Join-Path $ReleaseDir "WorkVPN-windows-amd64.zip"
New-Item -ItemType Directory -Force $ReleaseDir | Out-Null
Remove-Item -Recurse -Force $StageDir -ErrorAction SilentlyContinue
Remove-Item -Force $ZipPath -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $StageDir | Out-Null
Copy-Item "dist/WorkVPN.exe" $StageDir
Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $ZipPath -Force
Write-Host "Release: $ZipPath"

$Iscc = if ($env:ISCC) { $env:ISCC } else { "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" }
if (Test-Path $Iscc) {
    $SourceExe = (Resolve-Path "dist\WorkVPN.exe").Path
    $OutputDir = (Resolve-Path $ReleaseDir).Path
    & $Iscc "installer\WorkVPN.iss" "/DAppVersion=$Version" "/DAppArch=amd64" "/DSourceExe=$SourceExe" "/DAppArchMode=x64compatible" "/DOutputDir=$OutputDir" "/DOutputBaseFilename=WorkVPN-Setup-$Version-windows-amd64"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "Release: release\WorkVPN-Setup-$Version-windows-amd64.exe"
} else {
    Write-Host "Inno Setup not found, skipping setup build: $Iscc"
}
