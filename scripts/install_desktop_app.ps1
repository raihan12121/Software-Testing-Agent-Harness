# Atrocious Desktop App Installer for Windows
# Packages and installs Atrocious to %LOCALAPPDATA%\Programs\Atrocious
# Creates Desktop and Start Menu shortcuts

$ErrorActionPreference = "Stop"

$workspaceDir = Split-Path -Parent $PSScriptRoot
$appDir = "$env:LOCALAPPDATA\Programs\Atrocious"
$distDir = Join-Path $workspaceDir "dist\Atrocious"
$icoPath = Join-Path $workspaceDir "assets\atrocious.ico"

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "     Installing Atrocious QA Studio Desktop App     " -ForegroundColor Green
Write-Host "====================================================" -ForegroundColor Cyan

# 1. Ensure target directory exists
if (-not (Test-Path $appDir)) {
    New-Item -ItemType Directory -Force -Path $appDir | Out-Null
}

# 2. Copy application distribution
Write-Host "Copying application binaries to $appDir..." -ForegroundColor Yellow
Copy-Item -Path "$distDir\*" -Destination $appDir -Recurse -Force
Copy-Item -Path $icoPath -Destination $appDir -Force

# 3. Create Windows Shortcuts
$wsh = New-Object -ComObject WScript.Shell

# Desktop Shortcut
$desktopPath = [System.IO.Path]::Combine([Environment]::GetFolderPath("Desktop"), "Atrocious.lnk")
$shortcutDesktop = $wsh.CreateShortcut($desktopPath)
$shortcutDesktop.TargetPath = "$appDir\Atrocious.exe"
$shortcutDesktop.WorkingDirectory = $workspaceDir
$shortcutDesktop.IconLocation = "$appDir\atrocious.ico, 0"
$shortcutDesktop.Description = "Atrocious — Autonomous AI-First QA Desktop Workstation"
$shortcutDesktop.Save()
Write-Host "[✓] Desktop shortcut created: $desktopPath" -ForegroundColor Green

# Start Menu Shortcut
$startMenuPath = [System.IO.Path]::Combine([Environment]::GetFolderPath("Programs"), "Atrocious.lnk")
$shortcutStart = $wsh.CreateShortcut($startMenuPath)
$shortcutStart.TargetPath = "$appDir\Atrocious.exe"
$shortcutStart.WorkingDirectory = $workspaceDir
$shortcutStart.IconLocation = "$appDir\atrocious.ico, 0"
$shortcutStart.Description = "Atrocious — Autonomous AI-First QA Desktop Workstation"
$shortcutStart.Save()
Write-Host "[✓] Start Menu shortcut created: $startMenuPath" -ForegroundColor Green

Write-Host ""
Write-Host "Atrocious has been installed successfully!" -ForegroundColor Cyan
Write-Host "You can now launch Atrocious from your Desktop or Start Menu." -ForegroundColor White
