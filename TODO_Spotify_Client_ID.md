# TODO: Configure Spotify Client ID

## Current Status: ⏳ CHECK TOMORROW (Feb 11, 2026)

**Issue:** Spotify temporarily disabled new app creation in the Developer Dashboard.

**Update (2026-02-06):** Spotify announced Development Mode is reopening with new restrictions. See [blog post](https://developer.spotify.com/blog/2026-02-06-update-on-developer-access-and-platform-security).

**Action: Check [Developer Dashboard](https://developer.spotify.com/dashboard) on Feb 11, 2026** to create a new app.

**New Development Mode Requirements:**
- Spotify Premium account required
- One Client ID per developer
- Five authorized users max per Client ID
- Limited endpoint access (reduced scope)

**February 2026 API Changes ([details](https://developer.spotify.com/documentation/web-api/references/changes/february-2026)):**
- 15 endpoints removed (catalog browsing, other users' profiles/playlists)
- Playlist field restructuring: `tracks` → `items`
- Many fields removed (popularity, followers, available_markets, etc.)
- Your own playlists (`/me/playlists`) still work - app should be fine

---

## What's Been Completed ✅

- ✅ Application code is complete and deployed
- ✅ OAuth PKCE flow implemented correctly
- ✅ Docker container running on Unraid (port 8100)
- ✅ UI updated with login button
- ✅ App renamed to "Simon's Spotify Playlist Manager"
- ✅ Docker logging configured
- ✅ All code changes deployed

---

## What Needs to Be Done When Spotify Restores App Creation

### Step 1: Create Spotify App
1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Click "Create app" (when available)
3. Fill in:
   - **App name**: `Simon's Spotify Playlist Manager`
   - **App description**: `Personal playlist management tool`
   - **Redirect URI**: `http://192.168.2.110:8100/callback`
     - Click "Add" after entering
4. Click "Save"

### Step 2: Get Credentials
1. Copy **Client ID** (visible immediately)
2. Click "Show client secret" and copy **Client Secret**

### Step 3: Configure on Unraid Server
1. SSH to server: `ssh root@192.168.2.110`
2. Create/edit config file:
   ```bash
   nano /mnt/user/appdata/spotify-playlist-manager/spotify_config.json
   ```
3. Add this content (replace with actual values):
   ```json
   {
     "spotify": {
       "client_id": "YOUR_CLIENT_ID_HERE",
       "client_secret": "YOUR_CLIENT_SECRET_HERE",
       "redirect_uri": "http://192.168.2.110:8100/callback"
     }
   }
   ```
4. Save and exit (Ctrl+X, then Y, then Enter)

### Step 4: Test
1. Go to [http://192.168.2.110:8100](http://192.168.2.110:8100)
2. Click "LOGIN TO GET STARTED"
3. Should redirect to Spotify authorization page
4. Log in and authorize
5. Should see playlists after authorization

---

## How to Monitor for Updates

### Check These Sources Periodically:

1. **Developer Dashboard** (Primary)
   - [https://developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
   - Check if "Create app" button becomes active

2. **Developer Blog**
   - [https://developer.spotify.com/blog](https://developer.spotify.com/blog)
   - RSS Feed: [https://developer.spotify.com/rss.xml](https://developer.spotify.com/rss.xml)

3. **Community Forums**
   - [Main Forum](https://community.spotify.com/t5/Spotify-for-Developers/bd-p/Spotify_Developer)
   - [Discussion Thread 1](https://community.spotify.com/t5/Spotify-for-Developers/New-integrations-are-currently-on-hold/td-p/7296575)
   - [Discussion Thread 2](https://community.spotify.com/t5/Spotify-for-Developers/Unable-to-create-new-apps-New-integrations-are-currently-on-hold/td-p/7295590)

4. **Status Page**
   - [https://status.spotify.dev](https://status.spotify.dev)

---

## Important Notes

- **Redirect URI must match exactly**: `http://192.168.2.110:8100/callback`
- The app will automatically reload config when the file is updated
- If needed, restart container: `docker restart spotify-playlist-manager`
- Client ID is unique to your app and identifies it to Spotify
- Client Secret should be kept private (stored in config file, not in code)

---

## Timeline

- **Started waiting**: January 2025
- **2026-02-06**: Spotify published [update on developer access](https://developer.spotify.com/blog/2026-02-06-update-on-developer-access-and-platform-security)
- **2026-02-11**: New Development Mode Client IDs available under updated rules (Spotify Premium required, 1 Client ID per dev, 5 authorized users max)
- **2026-02-11**: **CHECK TOMORROW** - Try creating app in Developer Dashboard
- **2026-03-09**: Existing Development Mode integrations must comply with new requirements

---

## Related Files

- Application code: `spotify_app.py`
- Docker config: `docker-compose.yml`
- Config location on server: `/mnt/user/appdata/spotify-playlist-manager/spotify_config.json`
