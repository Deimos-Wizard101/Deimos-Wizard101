# build-clean.ps1
# Clean rebuild script for Deimos-Wizard101
#
# Usage:
#   .\build-clean.ps1
#   .\build-clean.ps1 -Yes
#   .\build-clean.ps1 -OpenDistFolder
#
# This script:
#   - Shows git changes
#   - Cleans build/dist
#   - Runs uv sync --dev
#   - Runs an AST syntax check
#   - Builds dist\Deimos.exe with PyInstaller
#   - Saves a build log under build-logs

param(
    [switch]$Yes,
    [switch]$OpenDistFolder
)

$ErrorActionPreference = "Stop"

$RepoPath = "C:\Users\sande\OneDrive\Desktop\Deimos-Wizard101"
$DistExe = Join-Path $RepoPath "dist\Deimos.exe"
$RootExe = Join-Path $RepoPath "Deimos.exe"
$BuildDir = Join-Path $RepoPath "build"
$DistDir = Join-Path $RepoPath "dist"
$LogDir = Join-Path $RepoPath "build-logs"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BuildLog = Join-Path $LogDir "build-$Timestamp.log"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "=== $Message ===" -ForegroundColor Cyan
}

function Write-LogLine {
    param([string]$Message)
    $Message | Out-File -FilePath $BuildLog -Append -Encoding utf8
}

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter(Mandatory = $false)]
        [string[]]$Arguments = @(),

        [Parameter(Mandatory = $false)]
        [string]$DisplayName = $FilePath
    )

    Write-Host ""
    Write-Host "> $DisplayName $($Arguments -join ' ')" -ForegroundColor DarkCyan
    Write-LogLine ""
    Write-LogLine "> $DisplayName $($Arguments -join ' ')"

    # Native commands sometimes write normal status text to stderr.
    # With $ErrorActionPreference = Stop, PowerShell can treat that stderr as fatal.
    # Temporarily relax it while the native command runs, then check $LASTEXITCODE ourselves.
    $oldErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    try {
        & $FilePath @Arguments 2>&1 | Tee-Object -FilePath $BuildLog -Append
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldErrorActionPreference
    }

    if ($null -eq $exitCode) {
        $exitCode = 0
    }

    if ($exitCode -ne 0) {
        throw "$DisplayName failed with exit code $exitCode. See log: $BuildLog"
    }
}

Write-Host ""
Write-Host "=== Deimos Clean Build ===" -ForegroundColor Cyan
Write-Host "Repo: $RepoPath"
Write-Host ""

Set-Location $RepoPath

if (!(Test-Path "Deimos.py")) {
    throw "Deimos.py not found. Are you in the correct repo folder?"
}

if (!(Test-Path "Deimos.spec")) {
    throw "Deimos.spec not found. Cannot build EXE."
}

if (!(Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

"=== Deimos Clean Build $Timestamp ===" | Out-File -FilePath $BuildLog -Encoding utf8
"Repo: $RepoPath" | Out-File -FilePath $BuildLog -Append -Encoding utf8

Write-Step "Git Status"
git status --short
Write-LogLine ""
Write-LogLine "=== Git Status ==="
git status --short | Out-File -FilePath $BuildLog -Append -Encoding utf8

Write-Host ""
Write-Host "=== Git Diff Summary ===" -ForegroundColor Cyan
git diff --stat
Write-LogLine ""
Write-LogLine "=== Git Diff Summary ==="
git diff --stat | Out-File -FilePath $BuildLog -Append -Encoding utf8

if (!$Yes) {
    Write-Host ""
    $confirm = Read-Host "Continue with clean rebuild? Type Y to continue"
    if ($confirm -ne "Y" -and $confirm -ne "y") {
        Write-Host "Build cancelled."
        exit 0
    }
}

if (Test-Path $RootExe) {
    Write-Host "Removing old root Deimos.exe..."
    Remove-Item $RootExe -Force
}

Write-Host "Cleaning old build/dist folders..."
Remove-Item $BuildDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $DistDir -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Checking uv..."
$uvCheck = Get-Command uv -ErrorAction SilentlyContinue
if (!$uvCheck) {
    throw "uv was not found. Install uv first, then rerun this script."
}

Write-Host "Checking for MSVC linker..."
$linkPath = cmd /c "where link 2>nul"

if ([string]::IsNullOrWhiteSpace($linkPath)) {
    Write-Host ""
    Write-Host "WARNING: link.exe was not found in this shell." -ForegroundColor Yellow
    Write-Host "This may be okay if dependencies are already built."
    Write-Host "If uv sync/build fails, open 'x64 Native Tools Command Prompt for VS 2022' and run this script from there."
    Write-Host ""
    Write-LogLine "WARNING: link.exe was not found in this shell."
}
else {
    Write-Host "Found link.exe:"
    Write-Host $linkPath
    Write-LogLine "Found link.exe: $linkPath"
}

Write-Step "uv sync --dev"
Invoke-Native -FilePath "uv" -Arguments @("sync", "--dev") -DisplayName "uv"

Write-Step "Python AST syntax check"

$AstCheckPath = Join-Path $env:TEMP "deimos_ast_check_$Timestamp.py"

$AstCheckCode = @'
import ast
from pathlib import Path

paths = [
    Path("Deimos.py"),
    Path("src"),
    Path("libs"),
]

bad = []

for base in paths:
    if not base.exists():
        continue

    if base.is_file():
        files = [base]
    else:
        files = list(base.rglob("*.py"))

    for file in files:
        # Ignore virtual env and generated build output just in case.
        text_path = str(file).replace("\\", "/").lower()
        if "/.venv/" in text_path or "/build/" in text_path or "/dist/" in text_path:
            continue

        try:
            ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        except Exception as e:
            bad.append((file, e))

if bad:
    for file, err in bad:
        print(f"SYNTAX ERROR: {file}: {err}")
    raise SystemExit(1)

print("AST syntax check passed.")
'@

$AstCheckCode | Out-File -FilePath $AstCheckPath -Encoding utf8

try {
    Invoke-Native -FilePath "uv" -Arguments @("run", "python", "-B", $AstCheckPath) -DisplayName "uv"
}
finally {
    Remove-Item $AstCheckPath -Force -ErrorAction SilentlyContinue
}

Write-Step "Building EXE with PyInstaller"
Invoke-Native -FilePath "uv" -Arguments @("run", "pyinstaller", "Deimos.spec", "--clean", "--noconfirm") -DisplayName "uv"

Write-Host ""

if (Test-Path $DistExe) {
    Write-Host "Build successful!" -ForegroundColor Green
    Write-Host "New EXE:"
    Write-Host $DistExe -ForegroundColor Green

    $file = Get-Item $DistExe
    Write-Host ""
    Write-Host "File size: $([math]::Round($file.Length / 1MB, 2)) MB"
    Write-Host "Modified: $($file.LastWriteTime)"

    Write-LogLine ""
    Write-LogLine "Build successful."
    Write-LogLine "New EXE: $DistExe"
    Write-LogLine "File size: $([math]::Round($file.Length / 1MB, 2)) MB"
    Write-LogLine "Modified: $($file.LastWriteTime)"
}
else {
    throw "Build finished, but dist\Deimos.exe was not found."
}

$logText = Get-Content $BuildLog -Raw -ErrorAction SilentlyContinue

if ($logText -match "ERROR: Hidden import") {
    Write-Host ""
    Write-Host "WARNING: PyInstaller reported hidden-import errors." -ForegroundColor Yellow
    Write-Host "The EXE still built, but test combat/questing in the EXE. If something works from source but not from EXE, the .spec file may need cleanup."
    Write-LogLine "WARNING: PyInstaller reported hidden-import errors."
}

if ($logText -match "WARNING: Hidden import") {
    Write-Host ""
    Write-Host "Note: PyInstaller reported hidden-import warnings. These are often harmless, but they are saved in the log." -ForegroundColor Yellow
    Write-LogLine "Note: PyInstaller reported hidden-import warnings."
}

Write-Host ""
Write-Host "Build log saved to:"
Write-Host $BuildLog -ForegroundColor Green

Write-Host ""
Write-Host "Optional next step: upload dist\Deimos.exe to VirusTotal."
Write-Host ""

if ($OpenDistFolder) {
    explorer.exe $DistDir
}
