# Deploy Spotify Playlist Manager files to Desktop folder
# This script copies the necessary files to the desktop folder for better performance
#
# DESTINATION: C:\Users\<username>\Desktop\Spotify Playlist Manager\
# This is where the app will run from - all config, tokens, and data files will be stored here

$desktopPath = "$env:USERPROFILE\Desktop\Spotify Playlist Manager"
$sourcePath = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) ".."

Write-Host "Deploying Spotify Playlist Manager files to Desktop..." -ForegroundColor Green
Write-Host "Source: $sourcePath" -ForegroundColor Yellow
Write-Host "Destination: $desktopPath" -ForegroundColor Yellow

# Create destination directory if it doesn't exist
if (!(Test-Path $desktopPath)) {
    New-Item -ItemType Directory -Path $desktopPath -Force
    Write-Host "Created directory: $desktopPath" -ForegroundColor Green
}

# Files to copy
$filesToCopy = @(
    "spotify_app.py",
    "spotify_config.json",
    "requirements.txt",
    "start_spotify.bat"
)

# Copy each file
foreach ($file in $filesToCopy) {
    $sourceFile = Join-Path $sourcePath $file
    $destFile = Join-Path $desktopPath $file
    
    if (Test-Path $sourceFile) {
        Copy-Item -Path $sourceFile -Destination $destFile -Force
        Write-Host "Copied: $file" -ForegroundColor Green
    } else {
        Write-Host "Warning: Source file not found: $file" -ForegroundColor Yellow
    }
}

# Copy templates directory
$templatesSource = Join-Path $sourcePath "templates"
$templatesDest = Join-Path $desktopPath "templates"

if (Test-Path $templatesSource) {
    if (Test-Path $templatesDest) {
        Remove-Item -Path $templatesDest -Recurse -Force
    }
    Copy-Item -Path $templatesSource -Destination $templatesDest -Recurse -Force
    Write-Host "Copied: templates/" -ForegroundColor Green
} else {
    Write-Host "Warning: Templates directory not found" -ForegroundColor Yellow
}

Write-Host "`nDeployment complete!" -ForegroundColor Green
Write-Host "Files are now available in: $desktopPath" -ForegroundColor Cyan
Write-Host "You can now run the Spotify app from the desktop folder." -ForegroundColor Cyan
Write-Host ""
Write-Host "⚠️  Note: spotify_config.json was deployed. Make sure to configure it with your Spotify credentials!" -ForegroundColor Yellow
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Edit spotify_config.json in the Desktop folder with your Spotify Client ID and Client Secret" -ForegroundColor Yellow
Write-Host "2. Add redirect URI to Spotify app: http://localhost:8081/callback (and http://<your-ip>:8081/callback for network access)" -ForegroundColor Yellow
Write-Host "3. Install Python dependencies: pip install -r requirements.txt" -ForegroundColor Yellow
Write-Host "4. Run: .\start_spotify.bat" -ForegroundColor Yellow
