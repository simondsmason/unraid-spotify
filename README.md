# Spotify Playlist Manager

Web application for managing Spotify playlists, built with FastAPI.

## Features

- ✅ Connect to Spotify via OAuth 2.0 (PKCE flow)
- ✅ List all your playlists
- 🚧 More features coming soon...

## Setup

### 1. Create Spotify App

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Click "Create App"
3. Fill in app details (name, description)
4. Add Redirect URIs:
   - `http://localhost:8081/callback` (for local access)
   - `http://<your-windows-ip>:8081/callback` (for network access, e.g., `http://192.168.1.100:8081/callback`)
5. Copy your **Client ID** and **Client Secret**

### 2. Configure

Edit `spotify_config.json`:
- Add your `client_id` and `client_secret`
- Update `redirect_uri` if needed (default: `http://localhost:8081/callback`)

### 3. Deploy to Desktop

**IMPORTANT:** The app runs from the Desktop folder, not the repository folder.

From the repository folder, run:
```powershell
.\Project - Deployment\deploy_to_desktop.ps1
```

This will copy all files to: `C:\Users\<your-username>\Desktop\Spotify Playlist Manager\`

**The app MUST run from the Desktop folder** - this is where it stores config, tokens, and data files.

### 4. Install Dependencies

On your Windows machine, in the Desktop folder:
```powershell
cd "$env:USERPROFILE\Desktop\Spotify Playlist Manager"
pip install -r requirements.txt
```

### 5. Run

**Manual:**
```powershell
.\start_spotify.bat
```

## Usage

1. Open browser to `http://localhost:8081` (or `http://<your-ip>:8081` from other machines)
2. Click "Connect to Spotify"
3. Authorize the app in Spotify
4. View your playlists!

## File Locations

**Working Folder** (repository):
- `spotify_app.py` - Main application
- `templates/` - Web UI templates
- `spotify_config.json` - Configuration template

**Execution Folder** (Desktop) - **THIS IS WHERE THE APP RUNS FROM:**
- Location: `C:\Users\<your-username>\Desktop\Spotify Playlist Manager\`
- `spotify_app.py` - Main application (copied from repo)
- `templates/` - Web UI templates (copied from repo)
- `spotify_config.json` - Your configured settings (edit this file here)
- `spotify_tokens.json` - Stored OAuth tokens (auto-generated, don't edit)
- `start_spotify.bat` - Startup script (run this to start the app)

## Port Configuration

- Default port: **8081**
- Change in `spotify_config.json` → `web.port`
- Make sure Windows Firewall allows the port if accessing from network

## Troubleshooting

### "Not authenticated" error
- Click "Logout" and reconnect
- Check that redirect URI matches in Spotify dashboard

### Can't access from network
- Check Windows Firewall allows port 8081
- Verify `host` is set to `0.0.0.0` in config
- Use your Windows machine's IP address in the URL

### OAuth errors
- Verify redirect URIs in Spotify dashboard match exactly
- Check Client ID and Secret are correct
- Make sure redirect URI includes the port number
