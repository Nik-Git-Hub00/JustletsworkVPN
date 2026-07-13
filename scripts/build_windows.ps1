param(
    [Alias("Arch")]
    [ValidateSet("native", "amd64", "arm64")]
    [string]$Architecture = "native"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }
& $Python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 'Python 3.11+ is required')"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$PythonMachine = (& $Python -c "import platform; print(platform.machine().lower())").Trim()
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$PythonArch = switch -Regex ($PythonMachine) {
    '^(amd64|x86_64)$' { "amd64"; break }
    '^(arm64|aarch64)$' { "arm64"; break }
    default { throw "Unsupported Python architecture: $PythonMachine" }
}

if ($Architecture -eq "native") {
    $Architecture = $PythonArch
} elseif ($Architecture -ne $PythonArch) {
    throw "PyInstaller cannot cross-compile Windows $Architecture from $PythonArch Python. Use a matching Python/runner."
}

$SpecPath = if ($Architecture -eq "arm64") { "specs/windows_arm64.spec" } else { "specs/windows.spec" }
$InnoArchMode = if ($Architecture -eq "arm64") { "arm64" } else { "x64compatible" }
$RuntimeDir = "runtime/windows-$Architecture"
$ReleaseArch = "windows-$Architecture"
$VenvDir = ".venv/windows-$Architecture"
$VenvPython = Join-Path $VenvDir "Scripts/python.exe"

$Version = if ($env:APP_VERSION) { $env:APP_VERSION } else { (Get-Content "VERSION" -First 1).Trim() }
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Invalid application version: $Version"
}
$env:APP_VERSION = $Version
if (-not $env:APP_UPDATE_REPO -and $env:GITHUB_REPOSITORY) { $env:APP_UPDATE_REPO = $env:GITHUB_REPOSITORY }
Write-Host "Building WorkVPN v$Version for $ReleaseArch"
if ($env:APP_UPDATE_REPO) { Write-Host "Update repository: $env:APP_UPDATE_REPO" }

if (-not (Test-Path $VenvPython)) {
    New-Item -ItemType Directory -Force (Split-Path -Parent $VenvDir) | Out-Null
    & $Python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$VenvMachine = (& $VenvPython -c "import platform; print(platform.machine().lower())").Trim()
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$VenvArch = switch -Regex ($VenvMachine) {
    '^(amd64|x86_64)$' { "amd64"; break }
    '^(arm64|aarch64)$' { "arm64"; break }
    default { throw "Unsupported virtual environment architecture: $VenvMachine" }
}
if ($VenvArch -ne $Architecture) {
    throw "Virtual environment architecture mismatch: expected $Architecture, found $VenvMachine. Remove $VenvDir and run the build again."
}

& $VenvPython -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 'Python 3.11+ is required in the virtual environment')"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $VenvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Test-Path "$RuntimeDir/sing-box.exe") -or -not (Test-Path "$RuntimeDir/libcronet.dll")) {
    ./scripts/fetch_runtime_windows.ps1 -Arch $Architecture
}

& $VenvPython -m PyInstaller --clean -y $SpecPath
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$ReleaseDir = "release"
$StageDir = Join-Path $ReleaseDir "WorkVPN-$ReleaseArch"
$ZipPath = Join-Path $ReleaseDir "WorkVPN-$ReleaseArch.zip"
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
    $SetupName = "WorkVPN-Setup-$Version-$ReleaseArch"
    & $Iscc "installer\WorkVPN.iss" "/DAppVersion=$Version" "/DAppArch=$Architecture" "/DSourceExe=$SourceExe" "/DAppArchMode=$InnoArchMode" "/DOutputDir=$OutputDir" "/DOutputBaseFilename=$SetupName"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "Release: release\$SetupName.exe"
} else {
    Write-Host "Inno Setup not found, skipping setup build: $Iscc"
}
