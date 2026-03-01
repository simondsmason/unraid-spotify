# Simon's Spotify Playlist Manager

Web application for managing Spotify playlists, built with FastAPI.

## Features

- ✅ Connect to Spotify via OAuth 2.0 (PKCE flow)
- ✅ Dashboard with tool launcher tiles
- ✅ Browse all playlists with track counts, owner, and visibility
- ✅ Playlist Mixer UI for combining playlists with mixing rules
- ✅ Debug logging toggle in settings

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

## Change History

- **1.00** - 2026-01-25 - Initial release
- **1.01** - 2026-02-13 - Added debug logging with toggle in settings page, added settings page
- **1.011** - 2026-02-13 - Fixed pagination bug: double /v1 in URL when fetching subsequent playlist pages
- **1.012** - 2026-02-13 - Fixed template error: tracks field renamed to items in Feb 2026 Spotify API
- **1.02** - 2026-02-13 - Dashboard restructured as tool launcher with tiles; playlist list moved to /playlists; added Playlist Mixer UI at /mixer
- **1.03** - 2026-02-14 - Filterable playlist dropdowns with type-to-search; added Merge and Limited Merge mixing rules
- **1.04** - 2026-02-14 - Mixer redesigned with Presets vs Custom Rules toggle; Merge and Limited Merge are now presets; custom rules placeholder for future
- **1.05** - 2026-02-16 - Implemented Merge and Limited Merge presets; browser tab titles now include app name suffix
- **1.06** - 2026-02-16 - Shuffle tracks before writing to output; default playlist selections; 403 retry logic; removed fields filter from tracks request
- **1.061** - 2026-02-16 - Fixed playlist track endpoints: /tracks renamed to /items per Feb 2026 Spotify API migration
- **1.07** - 2026-02-16 - Mixer shows all playlists with non-owned greyed out and unselectable; ownership validated before mixing
- **1.071** - 2026-02-16 - Fixed track extraction: Feb 2026 API renamed 'track' to 'item' inside playlist items response
- **1.072** - 2026-02-16 - Feb 2026 API audit: removed user-read-email scope (email field removed); fixed track count field priority in playlists template
- **1.08** - 2026-02-16 - Progress modal during mixing with live status; Docker container icon label; favicon
- **1.081** - 2026-02-16 - Added 429 rate-limit handling with Retry-After backoff in Spotify API calls
- **1.082** - 2026-02-16 - Fixed 504 timeout: moved playlist fetch and ownership validation into background thread
- **1.083** - 2026-02-16 - Fixed page hangs: changed routes with blocking Spotify API calls from async to sync (FastAPI threadpool)
- **1.084** - 2026-02-16 - Capped 429 Retry-After to 30s max; fail fast instead of sleeping for hours on heavy rate limits
- **1.085** - 2026-02-16 - Fixed pagination: rewrite next URL to /me/playlists (Spotify returns /users/{id}/playlists which is blocked in Dev Mode)
- **1.09** - 2026-02-26 - Added Ratio Mix preset: slider to set A/B percentage split, maximises output while maintaining ratio
- **1.091** - 2026-02-26 - Ratio slider moved to its own card above Mixing Method; slider labels show selected playlist names
- **1.10** - 2026-03-01 - Token validation: startup check, hourly background check, auto-clear on revoked tokens, Reconnect button
