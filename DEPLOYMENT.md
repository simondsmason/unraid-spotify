# Quick Deployment Guide

## Where Files Go

**Repository (development):**
- This folder (where you're editing code)

**Desktop (execution):**
- `C:\Users\<your-username>\Desktop\Spotify Playlist Manager\`
- **The app MUST run from here**

## Deployment Steps

1. **Run deployment script:**
   ```powershell
   .\Project - Deployment\deploy_to_desktop.ps1
   ```
   This copies files from repository → Desktop folder

2. **Go to Desktop folder:**
   ```powershell
   cd "$env:USERPROFILE\Desktop\Spotify Playlist Manager"
   ```

3. **Configure:**
   - Edit `spotify_config.json` with your Spotify Client ID and Secret

4. **Install dependencies (first time only):**
   ```powershell
   pip install -r requirements.txt
   ```

5. **Run:**
   ```powershell
   .\start_spotify.bat
   ```

## Important Notes

- ✅ App runs from **Desktop folder**, not repository folder
- ✅ Config file is in Desktop folder (edit there, not in repo)
- ✅ Tokens are stored in Desktop folder (auto-generated)
- ✅ After deploying, always work in the Desktop folder to run the app
- ✅ To update code: edit in repo, then run deployment script again

## File Locations Summary

| Item | Location |
|------|----------|
| Source code | Repository folder (this folder) |
| Running app | `Desktop\Spotify Playlist Manager\` |
| Config file | `Desktop\Spotify Playlist Manager\spotify_config.json` |
| Tokens | `Desktop\Spotify Playlist Manager\spotify_tokens.json` (auto) |
