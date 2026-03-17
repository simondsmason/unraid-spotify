# unraid-spotify Developer Notes

> Reference parent NOTES_TO_MYSELF.md for general coding standards, hub IPs, version conventions, and all other guidelines.

## Deployment

The app runs from the Desktop folder, not the repository folder.

**Desktop execution path:** `C:\Users\<your-username>\Desktop\Spotify Playlist Manager\`

### Deploy Steps

1. Run the deployment script from the repo:
   ```powershell
   .\Project - Deployment\deploy_to_desktop.ps1
   ```
2. Go to the Desktop folder:
   ```powershell
   cd "$env:USERPROFILE\Desktop\Spotify Playlist Manager"
   ```
3. Edit `spotify_config.json` with your Spotify Client ID and Secret
4. Install dependencies (first time only):
   ```powershell
   pip install -r requirements.txt
   ```
5. Run:
   ```powershell
   .\start_spotify.bat
   ```

### File Locations

| Item | Location |
|------|----------|
| Source code | Repository folder |
| Running app | `Desktop\Spotify Playlist Manager\` |
| Config file | `Desktop\Spotify Playlist Manager\spotify_config.json` |
| Tokens | `Desktop\Spotify Playlist Manager\spotify_tokens.json` (auto-generated) |

To update: edit in repo, then run the deployment script again.

## GitHub Repository Setup

- Repo: `https://github.com/simondsmason/unraid-spotify`
- `spotify_config.json` and `spotify_tokens.json` are excluded by `.gitignore` (contain secrets/tokens)

### Push Changes

```bash
git add .
git commit -m "Description of changes"
git push origin main
```
