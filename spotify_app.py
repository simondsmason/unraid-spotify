#!/usr/bin/env python3
"""
Simon's Spotify Playlist Manager
Web application for managing Spotify playlists.

Change History:
1.00 - 2026-01-25 - Initial release
1.01 - 2026-02-13 - Added debug logging with toggle in settings page, added settings page
1.011 - 2026-02-13 - Fixed pagination bug: double /v1 in URL when fetching subsequent playlist pages
1.012 - 2026-02-13 - Fixed template error: tracks field renamed to items in Feb 2026 Spotify API
1.02 - 2026-02-13 - Dashboard restructured as tool launcher with tiles; playlist list moved to /playlists; added Playlist Mixer UI at /mixer
1.03 - 2026-02-14 - Filterable playlist dropdowns with type-to-search; added Merge and Limited Merge mixing rules
1.04 - 2026-02-14 - Mixer redesigned with Presets vs Custom Rules toggle; Merge and Limited Merge are now presets; custom rules placeholder for future
1.05 - 2026-02-16 - Implemented Merge and Limited Merge presets; browser tab titles now include app name suffix
1.06 - 2026-02-16 - Shuffle tracks before writing to output; default playlist selections; 403 retry logic; removed fields filter from tracks request
1.061 - 2026-02-16 - Fixed playlist track endpoints: /tracks renamed to /items per Feb 2026 Spotify API migration
1.07 - 2026-02-16 - Mixer shows all playlists with non-owned greyed out and unselectable; ownership validated before mixing
1.071 - 2026-02-16 - Fixed track extraction: Feb 2026 API renamed 'track' to 'item' inside playlist items response
1.072 - 2026-02-16 - Feb 2026 API audit: removed user-read-email scope (email field removed); fixed track count field priority in playlists template
1.08 - 2026-02-16 - Progress modal during mixing with live status; Docker container icon label; favicon
1.081 - 2026-02-16 - Added 429 rate-limit handling with Retry-After backoff in Spotify API calls
1.082 - 2026-02-16 - Fixed 504 timeout: moved playlist fetch and ownership validation into background thread
1.083 - 2026-02-16 - Fixed page hangs: changed routes with blocking Spotify API calls from async to sync (FastAPI threadpool)
1.084 - 2026-02-16 - Capped 429 Retry-After to 30s max; fail fast instead of sleeping for hours on heavy rate limits
1.085 - 2026-02-16 - Fixed pagination: rewrite next URL to /me/playlists (Spotify returns /users/{id}/playlists which is blocked in Dev Mode)
1.09 - 2026-02-26 - Added Ratio Mix preset: slider to set A/B percentage split, maximises output while maintaining ratio
1.091 - 2026-02-26 - Ratio slider moved to its own card above Mixing Method; slider labels show selected playlist names
1.10 - 2026-03-01 - Token validation: startup check, hourly background check, auto-clear on revoked tokens, Reconnect button
1.11 - 2026-03-07 - UI restructure: replaced top nav with fixed left sidebar; removed redundant dashboard tiles
1.12 - 2026-03-07 - Dashboard tiles restored with Snapshots/Rules; placeholder pages for Snapshots/Rules; mixer modal stays open with OK/Save Preset buttons; mixer preset save/load/delete API
1.13 - 2026-03-07 - Snapshots: create, list, restore, delete point-in-time playlist copies; full snapshots UI with playlist dropdown and snapshot table
1.14 - 2026-03-07 - Rules/Scheduler: create, edit, toggle, delete scheduled rules; Run Preset and Snapshot actions; skip-if-unchanged condition; background scheduler daemon; Run Now with live status polling
1.15 - 2026-03-07 - Backup All Playlists rule action: snapshot all owned playlists in one rule, skip unchanged playlists via per-playlist hash tracking
1.16 - 2026-03-07 - Live progress updates during rule execution: per-playlist status for Backup All, step-by-step for Run Preset and Snapshot
1.17 - 2026-03-07 - Snapshots redesign: playlist grid view, click-through to detail with track list, snapshot version dropdown, restore/delete per snapshot
1.18 - 2026-03-07 - Moved snapshot storage from appdata to media volume (/mnt/user/media/Audio/spotify-backups/) via BACKUPS_DIR env var
"""

import datetime
import json
import logging
import os
import random
import sys
import secrets
import threading
import time
import uuid
import hashlib
import base64
import urllib.parse
import urllib.request
from typing import Optional, Dict, Any
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import uvicorn

# Version
VERSION = "1.18"

# Logging setup
logger = logging.getLogger("spotify_app")
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s (v%(version)s)",
                              defaults={"version": VERSION})
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Get execution directory
# Docker: Use DATA_DIR environment variable or /app/data
# Windows: Use Desktop folder
if os.getenv('DATA_DIR'):
    EXECUTION_DIR = os.getenv('DATA_DIR')
elif getattr(sys, 'frozen', False):
    # Running as compiled executable
    EXECUTION_DIR = os.path.dirname(sys.executable)
else:
    # Running as script - use Desktop folder
    EXECUTION_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "Spotify Playlist Manager")

# Ensure execution directory exists
os.makedirs(EXECUTION_DIR, exist_ok=True)

# Config file path (in execution directory)
CONFIG_FILE = os.path.join(EXECUTION_DIR, "spotify_config.json")

# Token storage path (in execution directory)
TOKEN_FILE = os.path.join(EXECUTION_DIR, "spotify_tokens.json")

# Global instances
app = FastAPI(title="Simon's Spotify Playlist Manager", version=VERSION)
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# Global state
config: Dict[str, Any] = {}
access_token: Optional[str] = None
refresh_token: Optional[str] = None
mixer_jobs: Dict[str, Dict[str, Any]] = {}


def set_debug_logging(enabled: bool):
    """Enable or disable debug logging (v{VERSION})."""
    if enabled:
        logger.setLevel(logging.DEBUG)
        logger.info("Debug logging ENABLED (v%s)", VERSION)
    else:
        logger.setLevel(logging.INFO)
        logger.info("Debug logging DISABLED (v%s)", VERSION)


def load_config() -> Dict[str, Any]:
    """Load configuration from file or environment variables (v{VERSION})."""
    # Priority: Environment variables > Config file > Defaults
    default_config = {
        "spotify": {
            "client_id": os.getenv('SPOTIFY_CLIENT_ID', ""),
            "client_secret": os.getenv('SPOTIFY_CLIENT_SECRET', ""),
            "redirect_uri": os.getenv('SPOTIFY_REDIRECT_URI', "")
        },
        "web": {
            "host": "0.0.0.0",
            "port": int(os.getenv('WEB_PORT', 8081))
        },
        "debug": False
    }

    # Load from file if it exists (file config overrides env vars if env vars are empty)
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            file_config = json.load(f)
            # Use file config if env vars are not set
            if file_config.get('spotify', {}).get('client_id') and not default_config['spotify']['client_id']:
                default_config['spotify']['client_id'] = file_config['spotify']['client_id']
            if file_config.get('spotify', {}).get('client_secret') and not default_config['spotify']['client_secret']:
                default_config['spotify']['client_secret'] = file_config['spotify']['client_secret']
            if file_config.get('spotify', {}).get('redirect_uri') and not default_config['spotify']['redirect_uri']:
                default_config['spotify']['redirect_uri'] = file_config['spotify']['redirect_uri']
            if file_config.get('web'):
                default_config['web'].update(file_config['web'])
            if 'debug' in file_config:
                default_config['debug'] = file_config['debug']

    # Apply debug logging setting
    set_debug_logging(default_config.get('debug', False))

    return default_config


def save_config(config_data: Dict[str, Any]):
    """Save configuration to file."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_data, f, indent=2)


def load_tokens() -> Dict[str, Any]:
    """Load stored tokens (v%s).""" % VERSION
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as f:
            tokens = json.load(f)
            logger.debug("Loaded tokens from file: access_token=%s chars, refresh_token=%s (v%s)",
                         len(tokens.get('access_token', '')) if tokens.get('access_token') else 'NONE',
                         'present' if tokens.get('refresh_token') else 'NONE', VERSION)
            return tokens
    logger.debug("No token file found at %s (v%s)", TOKEN_FILE, VERSION)
    return {}


def save_tokens(token_data: Dict[str, Any]):
    """Save tokens to file."""
    with open(TOKEN_FILE, 'w') as f:
        json.dump(token_data, f, indent=2)


def generate_code_verifier() -> str:
    """Generate PKCE code verifier."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')


def generate_code_challenge(verifier: str) -> str:
    """Generate PKCE code challenge from verifier."""
    digest = hashlib.sha256(verifier.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest).decode('utf-8').rstrip('=')


def get_spotify_auth_url(code_verifier: str, request: Optional[Request] = None) -> str:
    """Generate Spotify authorization URL."""
    code_challenge = generate_code_challenge(code_verifier)
    
    # Get redirect URI - use config if set, otherwise construct from request
    redirect_uri = config['spotify'].get('redirect_uri')
    if not redirect_uri and request:
        # Construct redirect URI from request
        scheme = request.url.scheme
        host = request.url.hostname
        port = request.url.port
        if port and port not in (80, 443):
            redirect_uri = f"{scheme}://{host}:{port}/callback"
        else:
            redirect_uri = f"{scheme}://{host}/callback"
    elif not redirect_uri:
        # Fallback default
        redirect_uri = "http://localhost:8081/callback"
    
    params = {
        'client_id': config['spotify']['client_id'],
        'response_type': 'code',
        'redirect_uri': redirect_uri,
        'scope': 'playlist-read-private playlist-read-collaborative playlist-modify-public playlist-modify-private user-read-private',
        'code_challenge_method': 'S256',
        'code_challenge': code_challenge
    }
    
    auth_url = 'https://accounts.spotify.com/authorize?' + urllib.parse.urlencode(params)
    return auth_url


def exchange_code_for_tokens(auth_code: str, code_verifier: str, redirect_uri: str) -> Dict[str, Any]:
    """Exchange authorization code for access and refresh tokens."""
    token_url = 'https://accounts.spotify.com/api/token'
    
    data = {
        'grant_type': 'authorization_code',
        'code': auth_code,
        'redirect_uri': redirect_uri,
        'client_id': config['spotify']['client_id'],
        'code_verifier': code_verifier
    }
    
    req = urllib.request.Request(
        token_url,
        data=urllib.parse.urlencode(data).encode('utf-8'),
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {error_body}")


def refresh_access_token() -> bool:
    """Refresh the access token using refresh token."""
    global access_token
    
    tokens = load_tokens()
    if not tokens.get('refresh_token'):
        return False
    
    token_url = 'https://accounts.spotify.com/api/token'
    
    auth_string = f"{config['spotify']['client_id']}:{config['spotify']['client_secret']}"
    auth_bytes = auth_string.encode('utf-8')
    auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
    
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': tokens['refresh_token']
    }
    
    req = urllib.request.Request(
        token_url,
        data=urllib.parse.urlencode(data).encode('utf-8'),
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {auth_b64}'
        }
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            access_token = result.get('access_token')

            # Update tokens
            tokens['access_token'] = access_token
            if 'refresh_token' in result:
                tokens['refresh_token'] = result['refresh_token']
            save_tokens(tokens)

            logger.info("Token refresh successful (v%s)", VERSION)
            return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else ''
        logger.error("Token refresh failed: %d %s (v%s)", e.code, error_body, VERSION)
        if 'invalid_grant' in error_body:
            logger.warning("Refresh token revoked, clearing stored tokens (v%s)", VERSION)
            save_tokens({})
            access_token = None
        return False
    except Exception as e:
        logger.error("Token refresh error: %s (v%s)", str(e), VERSION)
        return False


def get_spotify_api(endpoint: str, method: str = 'GET', data: Optional[Dict] = None) -> Dict[str, Any]:
    """Make API call to Spotify (v%s).""" % VERSION
    global access_token

    logger.debug("get_spotify_api called: endpoint=%s, method=%s (v%s)", endpoint, method, VERSION)

    # Load tokens if not loaded
    if not access_token:
        logger.debug("access_token is None, loading from file (v%s)", VERSION)
        tokens = load_tokens()
        access_token = tokens.get('access_token')

    if not access_token:
        logger.warning("No access token available after loading tokens (v%s)", VERSION)
        raise HTTPException(status_code=401, detail="Not authenticated. Please connect to Spotify.")

    url = f"https://api.spotify.com/v1{endpoint}"
    logger.debug("Spotify API request: %s %s (v%s)", method, url, VERSION)
    logger.debug("Access token: %s...%s (%d chars) (v%s)",
                 access_token[:10], access_token[-10:], len(access_token), VERSION)

    req_data = None
    if data:
        req_data = json.dumps(data).encode('utf-8')

    for attempt in range(4):  # Up to 3 retries for rate limits
        try:
            current_req = urllib.request.Request(
                url,
                data=req_data,
                method=method,
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json'
                }
            )
            with urllib.request.urlopen(current_req) as response:
                response_body = response.read().decode('utf-8')
                logger.debug("Spotify API response: status=%d, body_length=%d (v%s)",
                             response.status, len(response_body), VERSION)
                return json.loads(response_body)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            logger.error("Spotify API error: status=%d, url=%s, body=%s (v%s)",
                         e.code, url, error_body, VERSION)

            if e.code == 429:
                # Rate limited — wait and retry (cap at 30 seconds)
                retry_after = int(e.headers.get('Retry-After', 2))
                if retry_after > 30:
                    logger.error("Rate limit too long: %d seconds, giving up (v%s)", retry_after, VERSION)
                    raise HTTPException(status_code=429, detail=f"Spotify rate limit: retry after {retry_after}s. Please wait and try again.")
                logger.warning("Rate limited (429), waiting %d seconds before retry %d (v%s)",
                               retry_after, attempt + 1, VERSION)
                time.sleep(retry_after)
                continue

            if e.code in (401, 403):
                # Try to refresh token (403 can also indicate expired token in Dev Mode)
                logger.info("Got %d, attempting token refresh (v%s)", e.code, VERSION)
                if refresh_access_token():
                    logger.info("Token refresh successful, retrying request (v%s)", VERSION)
                    retry_req = urllib.request.Request(
                        url,
                        data=req_data,
                        method=method,
                        headers={
                            'Authorization': f'Bearer {access_token}',
                            'Content-Type': 'application/json'
                        }
                    )
                    try:
                        with urllib.request.urlopen(retry_req) as response:
                            response_body = response.read().decode('utf-8')
                            logger.debug("Retry successful: status=%d (v%s)", response.status, VERSION)
                            return json.loads(response_body)
                    except urllib.error.HTTPError as retry_e:
                        retry_error_body = retry_e.read().decode('utf-8')
                        logger.error("Retry also failed: status=%d, body=%s (v%s)",
                                     retry_e.code, retry_error_body, VERSION)
                        raise HTTPException(status_code=retry_e.code,
                                            detail=f"Spotify API error after retry: {retry_error_body}")
                else:
                    logger.error("Token refresh failed, clearing tokens (v%s)", VERSION)
                    save_tokens({})
                    access_token = None
                    raise HTTPException(status_code=401, detail="Authentication expired. Please reconnect.")
            else:
                raise HTTPException(status_code=e.code, detail=f"Spotify API error: {error_body}")

    # Exhausted all rate-limit retries
    raise HTTPException(status_code=429, detail="Spotify API rate limit exceeded after retries")


def get_current_user_id() -> Optional[str]:
    """Get the current authenticated user's Spotify ID."""
    try:
        result = get_spotify_api('/me')
        user_id = result.get('id')
        logger.debug("Current user ID: %s (v%s)", user_id, VERSION)
        return user_id
    except Exception as e:
        logger.error("Failed to get current user ID: %s (v%s)", str(e), VERSION)
        return None


def get_user_playlists() -> list:
    """Get all playlists for the current user (v%s).""" % VERSION
    logger.debug("Fetching user playlists (v%s)", VERSION)
    playlists = []
    url = '/me/playlists?limit=50'
    page = 1

    while url:
        logger.debug("Fetching playlist page %d: %s (v%s)", page, url, VERSION)
        result = get_spotify_api(url)
        items = result.get('items', [])
        playlists.extend(items)
        logger.debug("Page %d: got %d items, total so far: %d (v%s)", page, len(items), len(playlists), VERSION)
        url = result.get('next')
        if url:
            # Extract path from full URL, but force /me/playlists
            # Spotify may return /users/{id}/playlists which is blocked in Dev Mode
            url = url.replace('https://api.spotify.com/v1', '')
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            if 'offset' in params:
                url = f'/me/playlists?limit=50&offset={params["offset"][0]}'
            logger.debug("Next page URL (rewritten): %s (v%s)", url, VERSION)
        page += 1

    logger.info("Fetched %d playlists total (v%s)", len(playlists), VERSION)
    return playlists


def get_playlist_tracks(playlist_id: str, progress_callback=None) -> list:
    """Get all track URIs from a playlist."""
    logger.debug("Fetching tracks for playlist %s (v%s)", playlist_id, VERSION)
    track_uris = []
    url = f'/playlists/{playlist_id}/items?limit=100'

    while url:
        result = get_spotify_api(url)
        for item in result.get('items', []):
            # Feb 2026 API: 'track' renamed to 'item' inside playlist items
            track = item.get('item') or item.get('track')
            if track and track.get('uri'):
                track_uris.append(track['uri'])
        if progress_callback:
            progress_callback(len(track_uris))
        url = result.get('next')
        if url:
            url = url.replace('https://api.spotify.com/v1', '')

    logger.info("Fetched %d tracks from playlist %s (v%s)", len(track_uris), playlist_id, VERSION)
    return track_uris


def _calc_ratio_counts(total_a: int, total_b: int, pct_a: int, pct_b: int) -> tuple:
    """Calculate how many tracks to take from each playlist given a ratio.
    Maximises output while respecting available tracks and the ratio."""
    if pct_a == 0:
        return 0, total_b
    if pct_b == 0:
        return total_a, 0
    # Max output if A is the bottleneck vs B is the bottleneck
    max_from_a = total_a / (pct_a / 100)
    max_from_b = total_b / (pct_b / 100)
    max_total = min(max_from_a, max_from_b)
    count_a = round(max_total * pct_a / 100)
    count_b = round(max_total * pct_b / 100)
    return count_a, count_b


def replace_playlist_tracks(playlist_id: str, track_uris: list, progress_callback=None):
    """Replace all tracks in a playlist. Handles >100 track batches."""
    total = len(track_uris)
    logger.info("Writing %d tracks to playlist %s (v%s)", total, playlist_id, VERSION)

    # First batch uses PUT to replace (clears existing tracks)
    first_batch = track_uris[:100]
    get_spotify_api(f'/playlists/{playlist_id}/items', method='PUT', data={'uris': first_batch})
    if progress_callback:
        progress_callback(min(100, total), total)

    # Remaining batches use POST to append
    for i in range(100, total, 100):
        batch = track_uris[i:i + 100]
        get_spotify_api(f'/playlists/{playlist_id}/items', method='POST', data={'uris': batch})
        if progress_callback:
            progress_callback(min(i + 100, total), total)

    logger.info("Finished writing tracks to playlist %s (v%s)", playlist_id, VERSION)


# Startup event
@app.on_event("startup")
async def startup_event():
    global config
    config = load_config()
    logger.info("Configuration loaded: client_id=%s, redirect_uri=%s, debug=%s (v%s)",
                config['spotify']['client_id'][:8] + '...' if config['spotify']['client_id'] else 'NOT SET',
                config['spotify'].get('redirect_uri', 'NOT SET'),
                config.get('debug', False), VERSION)

    # Load and validate tokens
    tokens = load_tokens()
    global access_token
    access_token = tokens.get('access_token')
    logger.info("Startup: access_token=%s (v%s)",
                f"{len(access_token)} chars" if access_token else "NONE", VERSION)

    if access_token:
        _validate_token_at_startup()

    # Start background token health check
    token_check_thread = threading.Thread(target=_token_health_check_loop, daemon=True)
    token_check_thread.start()
    logger.info("Background token health check started (v%s)", VERSION)

    # Start scheduler
    scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
    scheduler_thread.start()
    logger.info("Rule scheduler started (v%s)", VERSION)


def _validate_token_at_startup():
    """Test the stored token with a lightweight API call. Clear if invalid."""
    global access_token
    try:
        req = urllib.request.Request(
            'https://api.spotify.com/v1/me',
            headers={'Authorization': f'Bearer {access_token}'}
        )
        with urllib.request.urlopen(req) as response:
            response.read()
            logger.info("Startup token validation: OK (v%s)", VERSION)
    except urllib.error.HTTPError as e:
        logger.warning("Startup token validation failed: %d (v%s)", e.code, VERSION)
        if e.code in (401, 403):
            logger.info("Attempting token refresh at startup (v%s)", VERSION)
            if not refresh_access_token():
                logger.warning("Startup refresh failed, clearing tokens (v%s)", VERSION)
                save_tokens({})
                access_token = None
            else:
                logger.info("Startup refresh successful (v%s)", VERSION)
    except Exception as e:
        logger.error("Startup token validation error: %s (v%s)", str(e), VERSION)


def _token_health_check_loop():
    """Background thread: validate token every hour, clear if revoked."""
    global access_token
    while True:
        time.sleep(3600)
        if not access_token:
            logger.debug("Token health check: no token, skipping (v%s)", VERSION)
            continue
        try:
            req = urllib.request.Request(
                'https://api.spotify.com/v1/me',
                headers={'Authorization': f'Bearer {access_token}'}
            )
            with urllib.request.urlopen(req) as response:
                response.read()
                logger.debug("Token health check: OK (v%s)", VERSION)
        except urllib.error.HTTPError as e:
            logger.warning("Token health check failed: %d (v%s)", e.code, VERSION)
            if e.code in (401, 403):
                if not refresh_access_token():
                    logger.warning("Token health check: refresh failed, clearing tokens (v%s)", VERSION)
                    save_tokens({})
                    access_token = None
                else:
                    logger.info("Token health check: refresh successful (v%s)", VERSION)
        except Exception as e:
            logger.error("Token health check error: %s (v%s)", str(e), VERSION)


# Routes
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    """Main dashboard - tool launcher page (v%s).""" % VERSION
    tokens = load_tokens()
    is_authenticated = bool(tokens.get('access_token'))
    is_configured = bool(config.get('spotify', {}).get('client_id'))

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "version": VERSION,
        "is_authenticated": is_authenticated,
        "is_configured": is_configured,
        "config": config,
    })


@app.get("/playlists", response_class=HTMLResponse)
def playlists_page(request: Request):
    """All playlists list page (v%s).""" % VERSION
    tokens = load_tokens()
    is_authenticated = bool(tokens.get('access_token'))
    is_configured = bool(config.get('spotify', {}).get('client_id'))

    playlists = []
    if is_authenticated:
        try:
            playlists = get_user_playlists()
            logger.debug("Playlists page: loaded %d playlists (v%s)", len(playlists), VERSION)
        except Exception as e:
            logger.error("Playlists page: failed to load playlists: %s (v%s)", str(e), VERSION)
            if "Not authenticated" in str(e) or "expired" in str(e).lower():
                save_tokens({})
                is_authenticated = False

    return templates.TemplateResponse("playlists.html", {
        "request": request,
        "version": VERSION,
        "is_authenticated": is_authenticated,
        "is_configured": is_configured,
        "playlists": playlists,
        "config": config,
    })


@app.get("/mixer", response_class=HTMLResponse)
def mixer_page(request: Request):
    """Playlist Mixer tool page (v%s).""" % VERSION
    tokens = load_tokens()
    is_authenticated = bool(tokens.get('access_token'))
    is_configured = bool(config.get('spotify', {}).get('client_id'))

    playlists = []
    user_id = None
    if is_authenticated:
        try:
            playlists = get_user_playlists()
            user_id = get_current_user_id()
            logger.debug("Mixer page: loaded %d playlists, user_id=%s (v%s)",
                         len(playlists), user_id, VERSION)
        except Exception as e:
            logger.error("Mixer page: failed to load playlists: %s (v%s)", str(e), VERSION)
            if "Not authenticated" in str(e) or "expired" in str(e).lower():
                save_tokens({})
                is_authenticated = False

    return templates.TemplateResponse("mixer.html", {
        "request": request,
        "version": VERSION,
        "is_authenticated": is_authenticated,
        "is_configured": is_configured,
        "playlists": playlists,
        "user_id": user_id or "",
        "config": config,
        "default_a": "Upbeat",
        "default_b": "Mellow Mix",
        "default_output": "MegaMix",
    })


@app.post("/mixer", response_class=HTMLResponse)
def mixer_action(
    request: Request,
    playlist_a: str = Form(""),
    playlist_b: str = Form(""),
    playlist_output: str = Form(""),
    mix_mode: str = Form("preset"),
    preset: str = Form("merge"),
    ratio_pct: int = Form(50),
):
    """Handle playlist mixing action (v%s).""" % VERSION
    tokens = load_tokens()
    is_authenticated = bool(tokens.get('access_token'))
    is_configured = bool(config.get('spotify', {}).get('client_id'))

    playlists = []
    user_id = None
    if is_authenticated:
        try:
            playlists = get_user_playlists()
            user_id = get_current_user_id()
        except Exception:
            pass

    mix_message = ""
    mix_error = False

    # Validate inputs
    if not playlist_a or not playlist_b or not playlist_output:
        mix_message = "Please select all three playlists."
        mix_error = True
    elif mix_mode != "preset":
        mix_message = "Custom rules are not yet available. Please use a Preset."
        mix_error = True
    else:
        # Validate ownership — only allow playlists the user owns
        owned_ids = {p.get('id') for p in playlists if p.get('owner', {}).get('id') == user_id} if user_id else set()
        for label, pid in [("Playlist A", playlist_a), ("Playlist B", playlist_b), ("Output playlist", playlist_output)]:
            if owned_ids and pid not in owned_ids:
                mix_message = f"{label} is not owned by you. You can only mix playlists you own."
                mix_error = True
                break

        if not mix_error:
            try:
                # Fetch tracks from both input playlists
                logger.info("Mixing: preset=%s, A=%s, B=%s, output=%s (v%s)",
                            preset, playlist_a, playlist_b, playlist_output, VERSION)

                tracks_a = get_playlist_tracks(playlist_a)
                tracks_b = get_playlist_tracks(playlist_b)

                if preset == "merge":
                    # Merge: all tracks from both playlists
                    combined = tracks_a + tracks_b
                    mix_message = f"Merge complete. Combined {len(tracks_a)} + {len(tracks_b)} = {len(combined)} tracks into the output playlist."

                elif preset == "limited_merge":
                    # Limited Merge: all from shorter + same count from longer
                    if len(tracks_a) <= len(tracks_b):
                        shorter = tracks_a
                        longer = tracks_b
                        shorter_label, longer_label = "A", "B"
                    else:
                        shorter = tracks_b
                        longer = tracks_a
                        shorter_label, longer_label = "B", "A"

                    limit = len(shorter)
                    combined = shorter + longer[:limit]
                    mix_message = (
                        f"Limited Merge complete. Took {len(shorter)} tracks from Playlist {shorter_label} "
                        f"and {limit} of {len(longer)} tracks from Playlist {longer_label}. "
                        f"Total: {len(combined)} tracks written to output."
                    )

                elif preset == "ratio":
                    # Ratio Mix: take tracks from each playlist based on percentage
                    pct_a = max(0, min(100, ratio_pct))
                    pct_b = 100 - pct_a
                    count_a, count_b = _calc_ratio_counts(len(tracks_a), len(tracks_b), pct_a, pct_b)
                    sample_a = random.sample(tracks_a, count_a) if count_a <= len(tracks_a) else tracks_a
                    sample_b = random.sample(tracks_b, count_b) if count_b <= len(tracks_b) else tracks_b
                    combined = sample_a + sample_b
                    mix_message = (
                        f"Ratio Mix complete ({pct_a}/{pct_b}). "
                        f"Took {count_a} of {len(tracks_a)} tracks from A "
                        f"and {count_b} of {len(tracks_b)} tracks from B. "
                        f"Total: {len(combined)} tracks written to output."
                    )
                else:
                    mix_message = f"Unknown preset: {preset}"
                    mix_error = True
                    combined = []

                if not mix_error and combined:
                    random.shuffle(combined)
                    replace_playlist_tracks(playlist_output, combined)

            except Exception as e:
                logger.error("Mixing failed: %s (v%s)", str(e), VERSION)
                mix_message = f"Mixing failed: {str(e)}"
                mix_error = True

    return templates.TemplateResponse("mixer.html", {
        "request": request,
        "version": VERSION,
        "is_authenticated": is_authenticated,
        "is_configured": is_configured,
        "playlists": playlists,
        "user_id": user_id or "",
        "config": config,
        "mix_message": mix_message,
    })


def run_mixer_job(job_id: str, playlist_a: str, playlist_b: str, playlist_output: str, preset: str, ratio_pct: int = 50):
    """Run a mixer job in a background thread. Updates mixer_jobs[job_id] with progress."""
    job = mixer_jobs[job_id]
    try:
        # Fetch playlists and validate ownership
        job['step'] = 'Validating playlists...'
        playlists = get_user_playlists()
        user_id = get_current_user_id()

        if user_id:
            owned_ids = {p.get('id') for p in playlists if p.get('owner', {}).get('id') == user_id}
            for label, pid in [("Playlist A", playlist_a), ("Playlist B", playlist_b), ("Output playlist", playlist_output)]:
                if pid not in owned_ids:
                    raise ValueError(f"{label} is not owned by you. You can only mix playlists you own.")

        # Look up playlist names for progress messages
        name_map = {p.get('id'): p.get('name', p.get('id')) for p in playlists}
        name_a = name_map.get(playlist_a, 'Playlist A')
        name_b = name_map.get(playlist_b, 'Playlist B')
        name_out = name_map.get(playlist_output, 'Output')

        # Read tracks from Playlist A
        job['status'] = 'reading'
        job['step'] = f'Reading {name_a}...'
        tracks_a = get_playlist_tracks(playlist_a, progress_callback=lambda count: job.update({'step': f'Reading {name_a}... {count} tracks'}))

        # Read tracks from Playlist B
        job['step'] = f'Reading {name_b}...'
        tracks_b = get_playlist_tracks(playlist_b, progress_callback=lambda count: job.update({'step': f'Reading {name_b}... {count} tracks'}))

        # Apply preset
        if preset == 'merge':
            combined = tracks_a + tracks_b
        elif preset == 'limited_merge':
            if len(tracks_a) <= len(tracks_b):
                shorter, longer = tracks_a, tracks_b
            else:
                shorter, longer = tracks_b, tracks_a
            limit = len(shorter)
            combined = shorter + longer[:limit]
        elif preset == 'ratio':
            pct_a = max(0, min(100, ratio_pct))
            pct_b = 100 - pct_a
            count_a, count_b = _calc_ratio_counts(len(tracks_a), len(tracks_b), pct_a, pct_b)
            combined = random.sample(tracks_a, count_a) + random.sample(tracks_b, count_b)
        else:
            raise ValueError(f'Unknown preset: {preset}')

        # Shuffle
        random.shuffle(combined)

        # Write to output
        job['status'] = 'writing'
        job['step'] = f'Writing to {name_out}... 0/{len(combined)}'
        replace_playlist_tracks(playlist_output, combined, progress_callback=lambda written, total: job.update({'step': f'Writing to {name_out}... {written}/{total}'}))

        # Build result message
        if preset == 'merge':
            msg = f'Merge complete. Combined {len(tracks_a)} + {len(tracks_b)} = {len(combined)} tracks into {name_out}.'
        elif preset == 'ratio':
            pct_a = max(0, min(100, ratio_pct))
            pct_b = 100 - pct_a
            msg = (f'Ratio Mix complete ({pct_a}/{pct_b}). '
                   f'Took {count_a} of {len(tracks_a)} tracks from {name_a} '
                   f'and {count_b} of {len(tracks_b)} tracks from {name_b}. '
                   f'Total: {len(combined)} tracks written to {name_out}.')
        else:
            if len(tracks_a) <= len(tracks_b):
                shorter_n, longer_n = name_a, name_b
                shorter_c, longer_c = len(tracks_a), len(tracks_b)
            else:
                shorter_n, longer_n = name_b, name_a
                shorter_c, longer_c = len(tracks_b), len(tracks_a)
            limit = shorter_c
            msg = f'Limited Merge complete. Took {shorter_c} tracks from {shorter_n} and {limit} of {longer_c} tracks from {longer_n}. Total: {len(combined)} tracks written to {name_out}.'

        job['status'] = 'done'
        job['step'] = msg
        logger.info("Mixer job %s completed: %s (v%s)", job_id, msg, VERSION)

    except Exception as e:
        logger.error("Mixer job %s failed: %s (v%s)", job_id, str(e), VERSION)
        job['status'] = 'error'
        job['step'] = f'Mixing failed: {str(e)}'


@app.post("/api/mixer")
async def api_mixer_start(request: Request):
    """Start a mixer job in the background. Returns job_id immediately for polling."""
    # Clean up old finished jobs (keep last 10 minutes)
    now = time.time()
    expired = [jid for jid, j in mixer_jobs.items() if j.get('created', 0) < now - 600]
    for jid in expired:
        del mixer_jobs[jid]

    tokens = load_tokens()
    if not tokens.get('access_token'):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    body = await request.json()
    playlist_a = body.get('playlist_a', '')
    playlist_b = body.get('playlist_b', '')
    playlist_output = body.get('playlist_output', '')
    preset = body.get('preset', 'merge')
    ratio_pct = body.get('ratio_pct', 50)

    if not playlist_a or not playlist_b or not playlist_output:
        return JSONResponse({"error": "Please select all three playlists."}, status_code=400)

    # Return job_id immediately — ownership validation and mixing happen in background thread
    job_id = str(uuid.uuid4())
    mixer_jobs[job_id] = {'status': 'starting', 'step': 'Validating playlists...', 'created': time.time()}

    thread = threading.Thread(target=run_mixer_job, args=(job_id, playlist_a, playlist_b, playlist_output, preset, ratio_pct), daemon=True)
    thread.start()

    return JSONResponse({"job_id": job_id})


@app.get("/api/mixer-status/{job_id}")
async def api_mixer_status(job_id: str):
    """Get the status of a mixer job."""
    job = mixer_jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    return JSONResponse({"status": job['status'], "step": job['step']})


# Mixer presets storage
PRESETS_FILE = os.path.join(EXECUTION_DIR, "mixer_presets.json")


def load_mixer_presets():
    """Load saved mixer presets from file (v%s).""" % VERSION
    if os.path.exists(PRESETS_FILE):
        try:
            with open(PRESETS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load mixer presets: %s (v%s)", str(e), VERSION)
    return []


def save_mixer_presets(presets):
    """Save mixer presets to file (v%s).""" % VERSION
    with open(PRESETS_FILE, 'w') as f:
        json.dump(presets, f, indent=2)
    logger.info("Saved %d mixer presets (v%s)", len(presets), VERSION)


@app.get("/api/mixer-presets")
async def api_get_mixer_presets():
    """List all saved mixer presets (v%s).""" % VERSION
    return JSONResponse(load_mixer_presets())


@app.post("/api/mixer-presets")
async def api_save_mixer_preset(request: Request):
    """Save a new mixer preset (v%s).""" % VERSION
    data = await request.json()
    name = data.get('name', '').strip()
    if not name:
        return JSONResponse({"error": "Preset name is required"}, status_code=400)

    presets = load_mixer_presets()
    preset = {
        "id": str(uuid.uuid4()),
        "name": name,
        "playlist_a": data.get('playlist_a', ''),
        "playlist_a_name": data.get('playlist_a_name', ''),
        "playlist_b": data.get('playlist_b', ''),
        "playlist_b_name": data.get('playlist_b_name', ''),
        "playlist_output": data.get('playlist_output', ''),
        "playlist_output_name": data.get('playlist_output_name', ''),
        "preset": data.get('preset', 'merge'),
        "ratio_pct": data.get('ratio_pct'),
        "created": datetime.datetime.now().isoformat()
    }
    presets.append(preset)
    save_mixer_presets(presets)
    logger.info("Saved mixer preset '%s' (v%s)", name, VERSION)
    return JSONResponse({"success": True, "id": preset["id"]})


@app.delete("/api/mixer-presets/{preset_id}")
async def api_delete_mixer_preset(preset_id: str):
    """Delete a saved mixer preset (v%s).""" % VERSION
    presets = load_mixer_presets()
    presets = [p for p in presets if p.get('id') != preset_id]
    save_mixer_presets(presets)
    logger.info("Deleted mixer preset %s (v%s)", preset_id, VERSION)
    return JSONResponse({"success": True})


# Snapshot storage — use BACKUPS_DIR env var (media volume), fall back to data dir
SNAPSHOTS_DIR = os.environ.get('BACKUPS_DIR', os.path.join(EXECUTION_DIR, "snapshots"))
os.makedirs(SNAPSHOTS_DIR, exist_ok=True)


def get_playlist_tracks_detail(playlist_id: str) -> list:
    """Get all tracks from a playlist with name/artist/URI for snapshots (v%s).""" % VERSION
    logger.debug("Fetching track details for playlist %s (v%s)", playlist_id, VERSION)
    tracks = []
    url = f'/playlists/{playlist_id}/items?limit=100'

    while url:
        result = get_spotify_api(url)
        for item in result.get('items', []):
            track = item.get('item') or item.get('track')
            if track and track.get('uri'):
                artists = track.get('artists', [])
                artist_name = artists[0].get('name', 'Unknown') if artists else 'Unknown'
                tracks.append({
                    'uri': track['uri'],
                    'name': track.get('name', 'Unknown'),
                    'artist': artist_name
                })
        url = result.get('next')
        if url:
            url = url.replace('https://api.spotify.com/v1', '')

    logger.info("Fetched %d track details from playlist %s (v%s)", len(tracks), playlist_id, VERSION)
    return tracks


def create_snapshot(playlist_id: str) -> dict:
    """Create a snapshot of a playlist. Returns the snapshot metadata (v%s).""" % VERSION
    # Get playlist name
    playlist_info = get_spotify_api(f'/playlists/{playlist_id}?fields=name')
    playlist_name = playlist_info.get('name', 'Unknown')

    # Get full track details
    tracks = get_playlist_tracks_detail(playlist_id)

    timestamp = datetime.datetime.now()
    snapshot = {
        'playlist_id': playlist_id,
        'playlist_name': playlist_name,
        'created': timestamp.isoformat(),
        'track_count': len(tracks),
        'tracks': tracks
    }

    filename = f"{playlist_id}_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join(SNAPSHOTS_DIR, filename)
    with open(filepath, 'w') as f:
        json.dump(snapshot, f, indent=2)

    logger.info("Created snapshot '%s' for playlist '%s' (%d tracks) (v%s)",
                filename, playlist_name, len(tracks), VERSION)
    return {'filename': filename, 'playlist_name': playlist_name, 'track_count': len(tracks), 'created': timestamp.isoformat()}


def list_snapshots() -> list:
    """List all saved snapshots with metadata (v%s).""" % VERSION
    snapshots = []
    for filename in sorted(os.listdir(SNAPSHOTS_DIR), reverse=True):
        if not filename.endswith('.json'):
            continue
        filepath = os.path.join(SNAPSHOTS_DIR, filename)
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            snapshots.append({
                'filename': filename,
                'playlist_id': data.get('playlist_id', ''),
                'playlist_name': data.get('playlist_name', 'Unknown'),
                'created': data.get('created', ''),
                'track_count': data.get('track_count', 0)
            })
        except Exception as e:
            logger.error("Failed to read snapshot %s: %s (v%s)", filename, str(e), VERSION)
    return snapshots


def restore_snapshot(filename: str) -> str:
    """Restore a snapshot to its playlist. Returns result message (v%s).""" % VERSION
    filepath = os.path.join(SNAPSHOTS_DIR, filename)
    if not os.path.exists(filepath):
        raise ValueError(f"Snapshot not found: {filename}")

    with open(filepath, 'r') as f:
        data = json.load(f)

    playlist_id = data['playlist_id']
    playlist_name = data.get('playlist_name', 'Unknown')
    track_uris = [t['uri'] for t in data.get('tracks', [])]

    if not track_uris:
        raise ValueError("Snapshot contains no tracks")

    replace_playlist_tracks(playlist_id, track_uris)
    msg = f"Restored {len(track_uris)} tracks to '{playlist_name}'"
    logger.info("Restored snapshot '%s': %s (v%s)", filename, msg, VERSION)
    return msg


@app.get("/api/snapshots")
async def api_list_snapshots():
    """List all snapshots (v%s).""" % VERSION
    return JSONResponse(list_snapshots())


@app.post("/api/snapshots")
async def api_create_snapshot(request: Request):
    """Create a snapshot of a playlist (v%s).""" % VERSION
    data = await request.json()
    playlist_id = data.get('playlist_id', '').strip()
    if not playlist_id:
        return JSONResponse({"error": "playlist_id is required"}, status_code=400)

    try:
        result = create_snapshot(playlist_id)
        return JSONResponse({"success": True, **result})
    except Exception as e:
        logger.error("Failed to create snapshot: %s (v%s)", str(e), VERSION)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.delete("/api/snapshots/{filename}")
async def api_delete_snapshot(filename: str):
    """Delete a snapshot (v%s).""" % VERSION
    filepath = os.path.join(SNAPSHOTS_DIR, filename)
    if not os.path.exists(filepath):
        return JSONResponse({"error": "Snapshot not found"}, status_code=404)
    os.remove(filepath)
    logger.info("Deleted snapshot %s (v%s)", filename, VERSION)
    return JSONResponse({"success": True})


@app.get("/api/snapshots/{filename}")
async def api_get_snapshot(filename: str):
    """Get a single snapshot with full track list (v%s).""" % VERSION
    filepath = os.path.join(SNAPSHOTS_DIR, filename)
    if not os.path.exists(filepath):
        return JSONResponse({"error": "Snapshot not found"}, status_code=404)
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        return JSONResponse(data)
    except Exception as e:
        logger.error("Failed to read snapshot %s: %s (v%s)", filename, str(e), VERSION)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/snapshots/{filename}/restore")
def api_restore_snapshot(filename: str):
    """Restore a snapshot to its playlist (v%s).""" % VERSION
    try:
        msg = restore_snapshot(filename)
        return JSONResponse({"success": True, "message": msg})
    except Exception as e:
        logger.error("Failed to restore snapshot: %s (v%s)", str(e), VERSION)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/snapshots", response_class=HTMLResponse)
def snapshots_page(request: Request):
    """Snapshots page (v%s).""" % VERSION
    tokens = load_tokens()
    is_authenticated = bool(tokens.get('access_token'))

    playlists = []
    user_id = None
    if is_authenticated:
        try:
            playlists = get_user_playlists()
            user_id = get_current_user_id()
        except Exception as e:
            logger.error("Snapshots page: failed to load playlists: %s (v%s)", str(e), VERSION)
            if "Not authenticated" in str(e) or "expired" in str(e).lower():
                save_tokens({})
                is_authenticated = False

    return templates.TemplateResponse("snapshots.html", {
        "request": request,
        "version": VERSION,
        "is_authenticated": is_authenticated,
        "config": config,
        "playlists": playlists,
        "user_id": user_id or "",
    })


# Rules storage and scheduler
RULES_FILE = os.path.join(EXECUTION_DIR, "rules.json")
rule_jobs: Dict[str, Dict[str, Any]] = {}


def load_rules() -> list:
    """Load rules from file (v%s).""" % VERSION
    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load rules: %s (v%s)", str(e), VERSION)
    return []


def save_rules(rules: list):
    """Save rules to file (v%s).""" % VERSION
    with open(RULES_FILE, 'w') as f:
        json.dump(rules, f, indent=2)


def _get_source_hash(preset: dict) -> str:
    """Get a hash of source playlist track URIs for skip-if-unchanged check."""
    try:
        tracks_a = get_playlist_tracks(preset['playlist_a'])
        tracks_b = get_playlist_tracks(preset['playlist_b'])
        combined = sorted(tracks_a + tracks_b)
        return hashlib.sha256('|'.join(combined).encode()).hexdigest()
    except Exception as e:
        logger.error("Failed to compute source hash: %s (v%s)", str(e), VERSION)
        return ''


def execute_rule(rule: dict, progress_cb=None) -> str:
    """Execute a single rule. Returns result message. progress_cb(msg) updates live status."""
    action = rule.get('action', '')

    def _progress(msg):
        if progress_cb:
            progress_cb(msg)

    if action == 'run_preset':
        preset_id = rule.get('config', {}).get('preset_id', '')
        presets = load_mixer_presets()
        preset = next((p for p in presets if p.get('id') == preset_id), None)
        if not preset:
            raise ValueError(f"Preset not found: {preset_id}")

        # Check skip_if_unchanged
        if rule.get('conditions', {}).get('skip_if_unchanged'):
            _progress("Checking if source playlists changed...")
            current_hash = _get_source_hash(preset)
            if current_hash and current_hash == rule.get('last_source_hash', ''):
                return 'Skipped — source playlists unchanged'
            rule['last_source_hash'] = current_hash

        # Run the mixer job synchronously
        _progress(f"Fetching tracks from '{preset.get('playlist_a_name', 'A')}'...")
        tracks_a = get_playlist_tracks(preset['playlist_a'])
        _progress(f"Fetching tracks from '{preset.get('playlist_b_name', 'B')}'...")
        tracks_b = get_playlist_tracks(preset['playlist_b'])

        mix_preset = preset.get('preset', 'merge')
        ratio_pct = preset.get('ratio_pct', 50) or 50

        _progress(f"Mixing {len(tracks_a)} + {len(tracks_b)} tracks...")
        if mix_preset == 'merge':
            combined = tracks_a + tracks_b
        elif mix_preset == 'limited_merge':
            if len(tracks_a) <= len(tracks_b):
                shorter, longer = tracks_a, tracks_b
            else:
                shorter, longer = tracks_b, tracks_a
            combined = shorter + longer[:len(shorter)]
        elif mix_preset == 'ratio':
            pct_a = max(0, min(100, ratio_pct))
            pct_b = 100 - pct_a
            count_a, count_b = _calc_ratio_counts(len(tracks_a), len(tracks_b), pct_a, pct_b)
            combined = random.sample(tracks_a, count_a) + random.sample(tracks_b, count_b)
        else:
            raise ValueError(f"Unknown preset type: {mix_preset}")

        random.shuffle(combined)
        _progress(f"Writing {len(combined)} tracks to '{preset.get('playlist_output_name', 'output')}'...")
        replace_playlist_tracks(preset['playlist_output'], combined)
        return f"Ran preset '{preset.get('name', '')}': {len(combined)} tracks written"

    elif action == 'snapshot':
        playlist_id = rule.get('config', {}).get('playlist_id', '')
        if not playlist_id:
            raise ValueError("No playlist configured for snapshot")
        _progress("Creating snapshot...")
        result = create_snapshot(playlist_id)
        return f"Snapshot created: {result['playlist_name']} ({result['track_count']} tracks)"

    elif action == 'backup_all':
        _progress("Fetching playlists...")
        user_id = get_current_user_id()
        if not user_id:
            raise ValueError("Not authenticated")
        all_playlists = get_user_playlists()
        owned = [p for p in all_playlists if p.get('owner', {}).get('id') == user_id]
        if not owned:
            return "Backup All: no owned playlists found"

        # Build hash map of previous snapshot hashes for skip-if-unchanged
        prev_hashes = rule.get('last_playlist_hashes', {})
        created = 0
        skipped = 0
        failed = 0
        total = len(owned)
        for i, pl in enumerate(owned, 1):
            pl_id = pl.get('id', '')
            pl_name = pl.get('name', 'Unknown')
            try:
                _progress(f"Checking {i}/{total}: {pl_name}")
                # Fetch current tracks to check for changes
                tracks = get_playlist_tracks(pl_id)
                current_hash = hashlib.sha256('|'.join(sorted(tracks)).encode()).hexdigest()

                if rule.get('conditions', {}).get('skip_if_unchanged'):
                    if current_hash == prev_hashes.get(pl_id, ''):
                        skipped += 1
                        continue

                _progress(f"Snapshotting {i}/{total}: {pl_name}")
                create_snapshot(pl_id)
                prev_hashes[pl_id] = current_hash
                created += 1
                logger.info("Backup All: snapshot created for '%s' (v%s)", pl_name, VERSION)
            except Exception as e:
                failed += 1
                logger.error("Backup All: failed to snapshot '%s': %s (v%s)", pl_name, str(e), VERSION)

        rule['last_playlist_hashes'] = prev_hashes
        parts = [f"{created} created"]
        if skipped:
            parts.append(f"{skipped} unchanged")
        if failed:
            parts.append(f"{failed} failed")
        return f"Backup All: {total} playlists — {', '.join(parts)}"

    else:
        raise ValueError(f"Unknown action: {action}")


def _run_rule_job(job_id: str, rule_id: str):
    """Run a rule in a background thread. Updates rule_jobs and rules.json."""
    job = rule_jobs[job_id]
    try:
        rules = load_rules()
        rule = next((r for r in rules if r.get('id') == rule_id), None)
        if not rule:
            raise ValueError(f"Rule not found: {rule_id}")

        def update_progress(msg):
            job['step'] = msg

        job['step'] = f"Starting: {rule.get('name', '')}..."
        msg = execute_rule(rule, progress_cb=update_progress)

        # Update rule status
        rule['last_run'] = datetime.datetime.now().isoformat()
        rule['last_result'] = msg
        save_rules(rules)

        job['status'] = 'done'
        job['step'] = msg
        logger.info("Rule '%s' completed: %s (v%s)", rule.get('name', ''), msg, VERSION)

    except Exception as e:
        logger.error("Rule job %s failed: %s (v%s)", job_id, str(e), VERSION)
        job['status'] = 'error'
        job['step'] = f'Failed: {str(e)}'
        # Update rule last_result with error
        try:
            rules = load_rules()
            rule = next((r for r in rules if r.get('id') == rule_id), None)
            if rule:
                rule['last_run'] = datetime.datetime.now().isoformat()
                rule['last_result'] = f'Error: {str(e)}'
                save_rules(rules)
        except Exception:
            pass


def _scheduler_loop():
    """Background scheduler: check rules every 60 seconds, run matching ones (v%s).""" % VERSION
    while True:
        time.sleep(60)
        try:
            rules = load_rules()
            now = datetime.datetime.now()
            current_time = now.strftime('%H:%M')
            current_day = now.strftime('%a').lower()

            for rule in rules:
                if not rule.get('enabled', False):
                    continue
                schedule = rule.get('schedule', {})
                rule_time = schedule.get('time', '')
                rule_days = schedule.get('days', [])

                if rule_time != current_time:
                    continue
                if rule_days and current_day not in rule_days:
                    continue

                # Check if already ran this minute
                last_run = rule.get('last_run', '')
                if last_run:
                    try:
                        last_dt = datetime.datetime.fromisoformat(last_run)
                        if (now - last_dt).total_seconds() < 90:
                            continue
                    except Exception:
                        pass

                logger.info("Scheduler: running rule '%s' (v%s)", rule.get('name', ''), VERSION)
                try:
                    msg = execute_rule(rule)
                    rule['last_run'] = now.isoformat()
                    rule['last_result'] = msg
                    logger.info("Scheduler: rule '%s' completed: %s (v%s)", rule.get('name', ''), msg, VERSION)
                except Exception as e:
                    rule['last_run'] = now.isoformat()
                    rule['last_result'] = f'Error: {str(e)}'
                    logger.error("Scheduler: rule '%s' failed: %s (v%s)", rule.get('name', ''), str(e), VERSION)

            save_rules(rules)
        except Exception as e:
            logger.error("Scheduler error: %s (v%s)", str(e), VERSION)


@app.get("/api/rules")
async def api_list_rules():
    """List all rules (v%s).""" % VERSION
    return JSONResponse(load_rules())


@app.post("/api/rules")
async def api_create_rule(request: Request):
    """Create a new rule (v%s).""" % VERSION
    data = await request.json()
    name = data.get('name', '').strip()
    if not name:
        return JSONResponse({"error": "Rule name is required"}, status_code=400)

    rule = {
        "id": str(uuid.uuid4()),
        "name": name,
        "enabled": data.get('enabled', True),
        "action": data.get('action', ''),
        "config": data.get('config', {}),
        "schedule": data.get('schedule', {}),
        "conditions": data.get('conditions', {}),
        "last_run": None,
        "last_result": None,
        "last_source_hash": None,
        "created": datetime.datetime.now().isoformat()
    }
    rules = load_rules()
    rules.append(rule)
    save_rules(rules)
    logger.info("Created rule '%s' (v%s)", name, VERSION)
    return JSONResponse({"success": True, "id": rule["id"]})


@app.put("/api/rules/{rule_id}")
async def api_update_rule(rule_id: str, request: Request):
    """Update a rule (v%s).""" % VERSION
    data = await request.json()
    rules = load_rules()
    rule = next((r for r in rules if r.get('id') == rule_id), None)
    if not rule:
        return JSONResponse({"error": "Rule not found"}, status_code=404)

    for key in ('name', 'enabled', 'action', 'config', 'schedule', 'conditions'):
        if key in data:
            rule[key] = data[key]
    save_rules(rules)
    logger.info("Updated rule '%s' (v%s)", rule.get('name', ''), VERSION)
    return JSONResponse({"success": True})


@app.delete("/api/rules/{rule_id}")
async def api_delete_rule(rule_id: str):
    """Delete a rule (v%s).""" % VERSION
    rules = load_rules()
    rules = [r for r in rules if r.get('id') != rule_id]
    save_rules(rules)
    logger.info("Deleted rule %s (v%s)", rule_id, VERSION)
    return JSONResponse({"success": True})


@app.post("/api/rules/{rule_id}/run")
async def api_run_rule(rule_id: str):
    """Run a rule immediately (v%s).""" % VERSION
    rules = load_rules()
    rule = next((r for r in rules if r.get('id') == rule_id), None)
    if not rule:
        return JSONResponse({"error": "Rule not found"}, status_code=404)

    job_id = str(uuid.uuid4())
    rule_jobs[job_id] = {'status': 'running', 'step': 'Starting...', 'created': time.time()}
    thread = threading.Thread(target=_run_rule_job, args=(job_id, rule_id), daemon=True)
    thread.start()
    return JSONResponse({"job_id": job_id})


@app.get("/api/rules/{rule_id}/status")
async def api_rule_status(rule_id: str):
    """Poll run status for a rule job. Uses rule_id as job_id param name but accepts job_id too."""
    job = rule_jobs.get(rule_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    return JSONResponse({"status": job['status'], "step": job['step']})


@app.get("/rules", response_class=HTMLResponse)
def rules_page(request: Request):
    """Rules page (v%s).""" % VERSION
    tokens = load_tokens()
    is_authenticated = bool(tokens.get('access_token'))

    playlists = []
    user_id = None
    if is_authenticated:
        try:
            playlists = get_user_playlists()
            user_id = get_current_user_id()
        except Exception as e:
            logger.error("Rules page: failed to load playlists: %s (v%s)", str(e), VERSION)
            if "Not authenticated" in str(e) or "expired" in str(e).lower():
                save_tokens({})
                is_authenticated = False

    return templates.TemplateResponse("rules.html", {
        "request": request,
        "version": VERSION,
        "is_authenticated": is_authenticated,
        "config": config,
        "playlists": playlists,
        "user_id": user_id or "",
    })


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    """Settings page (v%s).""" % VERSION
    tokens = load_tokens()
    is_authenticated = bool(tokens.get('access_token'))
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "version": VERSION,
        "is_authenticated": is_authenticated,
        "config": config,
        "debug_enabled": config.get('debug', False),
    })


@app.post("/settings")
def save_settings(request: Request, debug: Optional[str] = Form(None)):
    """Save settings (v%s).""" % VERSION
    global config
    debug_enabled = debug == "on"
    config['debug'] = debug_enabled
    logger.info("Settings updated: debug=%s (v%s)", debug_enabled, VERSION)

    # Save debug setting to config file
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            file_config = json.load(f)
    else:
        file_config = {}
    file_config['debug'] = debug_enabled
    with open(CONFIG_FILE, 'w') as f:
        json.dump(file_config, f, indent=2)

    set_debug_logging(debug_enabled)
    return RedirectResponse(url="/settings", status_code=303)


@app.get("/login")
async def login(request: Request):
    """Initiate Spotify OAuth login."""
    client_id = config.get('spotify', {}).get('client_id')
    if not client_id:
        return HTMLResponse(
            "<html><head><title>Configuration Required</title></head><body style='font-family: sans-serif; text-align: center; padding: 3rem;'>"
            "<h1>⚠️ Configuration Required</h1>"
            "<p><strong>Spotify Client ID is not configured.</strong></p>"
            "<p>To configure:</p>"
            "<ol style='text-align: left; max-width: 600px; margin: 1rem auto;'>"
            "<li>Set <code>SPOTIFY_CLIENT_ID</code> environment variable, OR</li>"
            "<li>Add <code>client_id</code> to <code>spotify_config.json</code> in the data directory</li>"
            "</ol>"
            "<p style='margin-top: 1rem;'><strong>Config file location:</strong><br>"
            f"<code>{EXECUTION_DIR}/spotify_config.json</code></p>"
            "<p style='margin-top: 2rem;'><a href='/' style='color: #1db954; text-decoration: none; font-weight: 600;'>← Go back</a></p>"
            "</body></html>"
        )
    
    code_verifier = generate_code_verifier()
    
    # Store verifier in session (for simplicity, we'll use a file-based approach)
    # In production, use proper session management
    verifier_file = os.path.join(EXECUTION_DIR, ".code_verifier")
    with open(verifier_file, 'w') as f:
        f.write(code_verifier)
    
    auth_url = get_spotify_auth_url(code_verifier, request)
    return RedirectResponse(url=auth_url)


@app.get("/callback")
async def callback(request: Request, code: Optional[str] = None, error: Optional[str] = None):
    """Handle OAuth callback from Spotify."""
    if error:
        return HTMLResponse(f"<h1>Authorization Error</h1><p>{error}</p>")
    
    if not code:
        return HTMLResponse("<h1>Error</h1><p>No authorization code received.</p>")
    
    # Load code verifier
    verifier_file = os.path.join(EXECUTION_DIR, ".code_verifier")
    if not os.path.exists(verifier_file):
        return HTMLResponse("<h1>Error</h1><p>Code verifier not found. Please try logging in again.</p>")
    
    with open(verifier_file, 'r') as f:
        code_verifier = f.read().strip()
    
    # Clean up verifier file
    os.remove(verifier_file)
    
    # Construct redirect URI from request (must match the one used in authorization)
    scheme = request.url.scheme
    host = request.url.hostname
    port = request.url.port
    if port and port not in (80, 443):
        redirect_uri = f"{scheme}://{host}:{port}/callback"
    else:
        redirect_uri = f"{scheme}://{host}/callback"
    
    # Use config redirect_uri if set, otherwise use constructed one
    if config['spotify'].get('redirect_uri'):
        redirect_uri = config['spotify']['redirect_uri']
    
    # Exchange code for tokens
    try:
        token_data = exchange_code_for_tokens(code, code_verifier, redirect_uri)
        
        # Save tokens
        save_tokens({
            'access_token': token_data['access_token'],
            'refresh_token': token_data.get('refresh_token'),
            'expires_in': token_data.get('expires_in', 3600)
        })
        
        global access_token
        access_token = token_data['access_token']
        
        return RedirectResponse(url="/")
    except Exception as e:
        return HTMLResponse(f"<h1>Error</h1><p>Failed to exchange tokens: {str(e)}</p>")


@app.get("/logout")
async def logout():
    """Logout and clear tokens."""
    save_tokens({})
    global access_token
    access_token = None
    return RedirectResponse(url="/")


@app.get("/api/playlists")
def api_playlists():
    """Get all playlists (API endpoint)."""
    try:
        playlists = get_user_playlists()
        return {"playlists": playlists}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/status")
async def api_status():
    """Get authentication status."""
    tokens = load_tokens()
    return {
        "authenticated": bool(tokens.get('access_token')),
        "version": VERSION
    }


@app.get("/api/check-token")
def api_check_token():
    """Actively validate the stored token against Spotify API."""
    global access_token
    tokens = load_tokens()
    if not tokens.get('access_token'):
        return {"valid": False, "reason": "No token stored"}

    access_token = tokens.get('access_token')
    try:
        req = urllib.request.Request(
            'https://api.spotify.com/v1/me',
            headers={'Authorization': f'Bearer {access_token}'}
        )
        with urllib.request.urlopen(req) as response:
            response.read()
            logger.info("Token check: valid (v%s)", VERSION)
            return {"valid": True}
    except urllib.error.HTTPError as e:
        logger.warning("Token check failed: %d (v%s)", e.code, VERSION)
        if e.code in (401, 403):
            if not refresh_access_token():
                logger.warning("Token check: refresh failed, clearing tokens (v%s)", VERSION)
                save_tokens({})
                access_token = None
                return {"valid": False, "reason": "Token expired or revoked"}
            else:
                logger.info("Token check: refreshed successfully (v%s)", VERSION)
                return {"valid": True}
        return {"valid": False, "reason": f"Spotify API error: {e.code}"}
    except Exception as e:
        logger.error("Token check error: %s (v%s)", str(e), VERSION)
        return {"valid": False, "reason": str(e)}


def main():
    """Main entry point."""
    global config
    config = load_config()
    
    web_config = config.get('web', {})
    host = web_config.get('host', '0.0.0.0')
    port = web_config.get('port', 8081)
    
    # Startup Banner
    print("\n" + "="*50)
    print(f"  Simon's Spotify Playlist Manager v{VERSION}")
    print("="*50)
    print(f"  Web Interface   : http://localhost:{port}")
    print(f"  API Endpoint    : http://localhost:{port}/api")
    print(f"  Execution Dir   : {EXECUTION_DIR}")
    print("="*50 + "\n")
    print("Starting web server...")
    
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
