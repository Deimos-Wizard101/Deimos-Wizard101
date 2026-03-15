# Deimos Version Bump and Release Script
# Usage: .\release.ps1 [major|minor|patch]

param(
    [Parameter(Position=0)]
    [ValidateSet("major", "minor", "patch")]
    [string]$BumpType = "patch"
)

# Colors for output
function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

function Write-Green { Write-ColorOutput Green $args }
function Write-Yellow { Write-ColorOutput Yellow $args }
function Write-Red { Write-ColorOutput Red $args }
function Write-Blue { Write-ColorOutput Blue $args }

Write-Green "🚀 Deimos Release Script"
Write-Blue "Bump type: $BumpType"

# Branch check removed - user will handle branch management

# Check for uncommitted changes
$status = git status --porcelain
if ($status) {
    Write-Red "❌ Error: You have uncommitted changes"
    git status --short
    exit 1
}

# Pull latest changes
Write-Blue "📥 Pulling latest changes..."
git pull origin main

# Get current version from Deimos.py source code
Write-Blue "📖 Reading current version from Deimos.py..."
if (-not (Test-Path "Deimos.py")) {
    Write-Red "❌ Error: Deimos.py not found in current directory"
    exit 1
}

$content = Get-Content "Deimos.py" -Raw
$versionMatch = $content | Select-String "tool_version: str = '([^']+)'"

if (-not $versionMatch) {
    Write-Red "❌ Error: Could not find tool_version in Deimos.py"
    exit 1
}

$currentVersionNumber = $versionMatch.Matches[0].Groups[1].Value
$currentVersion = "v$currentVersionNumber"

Write-Blue "Current version: $currentVersion"

# Remove 'v' prefix for version manipulation
$versionNumber = $currentVersionNumber

# Split version into parts
$versionParts = $versionNumber.Split('.')
$major = [int]($versionParts[0] -replace '[^\d]','')
$minor = if ($versionParts.Count -gt 1) { [int]($versionParts[1] -replace '[^\d]','') } else { 0 }
$patch = if ($versionParts.Count -gt 2) { [int]($versionParts[2] -replace '[^\d]','') } else { 0 }

# Bump version based on type
switch ($BumpType) {
    "major" {
        $major++
        $minor = 0
        $patch = 0
    }
    "minor" {
        $minor++
        $patch = 0
    }
    "patch" {
        $patch++
    }
}

$newVersion = "v$major.$minor.$patch"
$newVersionNumber = "$major.$minor.$patch"
Write-Green "New version: $newVersion"

# Show what will be included in this release
Write-Blue "📝 Changes since last release:"
if ($currentVersion -ne "v0.0.0") {
    git log "$currentVersion..HEAD" --oneline --no-merges | Select-Object -First 10
} else {
    git log --oneline --no-merges | Select-Object -First 10
}

Write-Host ""
$confirm = Read-Host "Create and push release $newVersion? (y/N)"
if ($confirm -ne "y" -and $confirm -ne "Y") {
    Write-Host "Release cancelled."
    exit 0
}

# Update version in Deimos.py if it exists
if (Test-Path "Deimos.py") {
    Write-Yellow "📝 Updating version in Deimos.py..."
    
    # Read the file content
    $content = Get-Content "Deimos.py" -Raw
    
    # Update the tool_version variable
    $pattern = "tool_version: str = '[^']*'"
    $replacement = "tool_version: str = '$newVersionNumber'"
    $newContent = $content -replace $pattern, $replacement
    
    # Write back to file
    Set-Content "Deimos.py" -Value $newContent -NoNewline
    
    # Show the change
    Write-Blue "Version updated in Deimos.py:"
    Select-String -Path "Deimos.py" -Pattern "tool_version:"
    
    # Commit version file changes
    git add Deimos.py
    git commit -m "Bump version to $newVersion"
}

# Update version in version_info.txt if it exists
if (Test-Path "version_info.txt") {
    Write-Yellow "📝 Updating version_info.txt..."
    
    $content = Get-Content "version_info.txt" -Raw
    
    # Update version numbers
    $content = $content -replace "filevers=\([0-9,]*\)", "filevers=($major,$minor,$patch,0)"
    $content = $content -replace "prodvers=\([0-9,]*\)", "prodvers=($major,$minor,$patch,0)"
    $content = $content -replace "'FileVersion', '[^']*'", "'FileVersion', '$newVersionNumber.0'"
    $content = $content -replace "'ProductVersion', '[^']*'", "'ProductVersion', '$newVersionNumber.0'"
    
    Set-Content "version_info.txt" -Value $content -NoNewline
    
    # Check if there are changes to commit
    $diff = git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        git add version_info.txt
        git commit -m "Update version_info.txt to $newVersion"
    }
}

# Create and push tag
Write-Yellow "🏷️  Creating tag..."

# Generate changelog for tag message
$changelog = if ($currentVersion -ne "v0.0.0") {
    git log "$currentVersion..HEAD" --pretty=format:"- %s" --no-merges
} else {
    "- Initial release"
}

$tagMessage = @"
Release $newVersion

$changelog
"@

git tag -a "$newVersion" -m $tagMessage

Write-Yellow "🚀 Pushing changes and tag to trigger release..."
git push origin main  # Push any version file changes
git push origin "$newVersion"  # Push the tag

Write-Host ""
Write-Green "✅ Release $newVersion initiated!"
Write-Green "🔗 Check the release progress at:"

# Get repository URL
$repoUrl = git config --get remote.origin.url
$repoPath = $repoUrl -replace '.*github\.com[:/]([^.]*)(\.git)?.*', '$1'

Write-Blue "   https://github.com/$repoPath/actions"
Write-Host ""
Write-Green "📦 Once complete, the release will be available at:"
Write-Blue "   https://github.com/$repoPath/releases/tag/$newVersion"

Write-Host ""
Write-Yellow "📋 Release will include:"
Write-Host "   • Deimos.exe (compiled application)"
Write-Host "   • Deimos-config.ini (configuration file)"
Write-Host "   • LICENSE (license information)"
Write-Host "   • All packaged in: Deimos-$newVersion.zip"