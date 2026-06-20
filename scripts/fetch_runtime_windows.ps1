param(
    [ValidateSet("amd64", "arm64", "all")]
    [string]$Arch = "all"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$Version = if ($env:SING_BOX_VERSION) { $env:SING_BOX_VERSION } else { "1.13.13" }
$BaseUrl = "https://github.com/SagerNet/sing-box/releases/download/v$Version"
$TmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) "workvpn-sing-box-$Version"

function Fetch-One([string]$TargetArch) {
    $ArchiveName = "sing-box-$Version-windows-$TargetArch.zip"
    $Url = "$BaseUrl/$ArchiveName"
    $Work = Join-Path $TmpRoot "windows-$TargetArch"
    $Zip = Join-Path $Work $ArchiveName
    $Extract = Join-Path $Work "extract"
    $TargetDir = Join-Path "runtime" "windows-$TargetArch"

    New-Item -ItemType Directory -Force -Path $Work, $Extract, $TargetDir | Out-Null
    Write-Host "Downloading $Url"
    Invoke-WebRequest -Uri $Url -OutFile $Zip
    if (Test-Path $Extract) { Remove-Item -Recurse -Force $Extract }
    New-Item -ItemType Directory -Force -Path $Extract | Out-Null
    Expand-Archive -Path $Zip -DestinationPath $Extract -Force

    $SourceDir = Get-ChildItem -Path $Extract -Directory -Filter "sing-box-*" | Select-Object -First 1
    if (-not $SourceDir) { throw "Extracted sing-box directory not found" }
    Copy-Item -Force (Join-Path $SourceDir.FullName "sing-box.exe") (Join-Path $TargetDir "sing-box.exe")
    Copy-Item -Force (Join-Path $SourceDir.FullName "libcronet.dll") (Join-Path $TargetDir "libcronet.dll")
    Copy-Item -Force (Join-Path $SourceDir.FullName "LICENSE") (Join-Path $TargetDir "LICENSE")
}

if ($Arch -eq "all") {
    Fetch-One "amd64"
    Fetch-One "arm64"
} else {
    Fetch-One $Arch
}
