#!/usr/bin/env python3
"""
Spotify Playlist Manager
Web application for managing Spotify playlists.
"""

import json
import os
import sys
import secrets
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
VERSION = "1.00"

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
app = FastAPI(title="Spotify Playlist Manager", version=VERSION)
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# Global state
config: Dict[str, Any] = {}
access_token: Optional[str] = None
refresh_token: Optional[str] = None


def load_config() -> Dict[str, Any]:
    """Load configuration from file or environment variables."""
    # Priority: Environment variables > Config file > Defaults
    default_config = {
        "spotify": {
            "client_id": os.getenv('SPOTIFY_CLIENT_ID', ""),
            "client_secret": os.getenv('SPOTIFY_CLIENT_SECRET', ""),
            "redirect_uri": os.getenv('SPOTIFY_REDIRECT_URI', "http://localhost:8081/callback")
        },
        "web": {
            "host": "0.0.0.0",
            "port": int(os.getenv('WEB_PORT', 8081))
        }
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
    
    return default_config


def save_config(config_data: Dict[str, Any]):
    """Save configuration to file."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_data, f, indent=2)


def load_tokens() -> Dict[str, Any]:
    """Load stored tokens."""
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as f:
            return json.load(f)
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


def get_spotify_auth_url(code_verifier: str) -> str:
    """Generate Spotify authorization URL."""
    code_challenge = generate_code_challenge(code_verifier)
    
    params = {
        'client_id': config['spotify']['client_id'],
        'response_type': 'code',
        'redirect_uri': config['spotify']['redirect_uri'],
        'scope': 'playlist-read-private playlist-read-collaborative playlist-modify-public playlist-modify-private user-read-private user-read-email',
        'code_challenge_method': 'S256',
        'code_challenge': code_challenge
    }
    
    auth_url = 'https://accounts.spotify.com/authorize?' + urllib.parse.urlencode(params)
    return auth_url


def exchange_code_for_tokens(auth_code: str, code_verifier: str) -> Dict[str, Any]:
    """Exchange authorization code for access and refresh tokens."""
    token_url = 'https://accounts.spotify.com/api/token'
    
    data = {
        'grant_type': 'authorization_code',
        'code': auth_code,
        'redirect_uri': config['spotify']['redirect_uri'],
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
            
            return True
    except Exception as e:
        return False


def get_spotify_api(endpoint: str, method: str = 'GET', data: Optional[Dict] = None) -> Dict[str, Any]:
    """Make API call to Spotify."""
    global access_token
    
    # Load tokens if not loaded
    if not access_token:
        tokens = load_tokens()
        access_token = tokens.get('access_token')
    
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated. Please connect to Spotify.")
    
    url = f"https://api.spotify.com/v1{endpoint}"
    
    req_data = None
    if data:
        req_data = json.dumps(data).encode('utf-8')
    
    req = urllib.request.Request(
        url,
        data=req_data,
        method=method,
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            # Try to refresh token
            if refresh_access_token():
                # Retry request
                req.headers['Authorization'] = f'Bearer {access_token}'
                with urllib.request.urlopen(req) as response:
                    return json.loads(response.read().decode('utf-8'))
            else:
                raise HTTPException(status_code=401, detail="Authentication expired. Please reconnect.")
        else:
            error_body = e.read().decode('utf-8')
            raise HTTPException(status_code=e.code, detail=f"Spotify API error: {error_body}")


def get_user_playlists() -> list:
    """Get all playlists for the current user."""
    playlists = []
    url = '/me/playlists?limit=50'
    
    while url:
        result = get_spotify_api(url)
        playlists.extend(result.get('items', []))
        url = result.get('next')
        if url:
            # Extract path from full URL
            url = url.replace('https://api.spotify.com', '')
    
    return playlists


# Startup event
@app.on_event("startup")
async def startup_event():
    global config
    config = load_config()
    
    # Load tokens
    tokens = load_tokens()
    global access_token
    access_token = tokens.get('access_token')


# Routes
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page."""
    tokens = load_tokens()
    is_authenticated = bool(tokens.get('access_token'))
    
    # Check if Spotify is configured (Client ID must be set)
    is_configured = bool(config.get('spotify', {}).get('client_id'))
    
    playlists = []
    if is_authenticated:
        try:
            playlists = get_user_playlists()
        except Exception as e:
            # If auth fails, clear tokens
            if "Not authenticated" in str(e) or "expired" in str(e).lower():
                save_tokens({})
                is_authenticated = False
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "version": VERSION,
        "is_authenticated": is_authenticated,
        "is_configured": is_configured,
        "playlists": playlists,
        "config": config,
    })


# Settings page removed - credentials are now configured via config file or environment variables
# Users just click "Login to Spotify" and authorize


@app.get("/login")
async def login():
    """Initiate Spotify OAuth login."""
    client_id = config.get('spotify', {}).get('client_id')
    if not client_id:
        return HTMLResponse(
            "<h1>Configuration Error</h1>"
            "<p>Spotify Client ID is not configured.</p>"
            "<p>Please set <code>SPOTIFY_CLIENT_ID</code> environment variable or add it to <code>spotify_config.json</code>.</p>"
            "<p><a href='/'>Go back</a></p>"
        )
    
    code_verifier = generate_code_verifier()
    
    # Store verifier in session (for simplicity, we'll use a file-based approach)
    # In production, use proper session management
    verifier_file = os.path.join(EXECUTION_DIR, ".code_verifier")
    with open(verifier_file, 'w') as f:
        f.write(code_verifier)
    
    auth_url = get_spotify_auth_url(code_verifier)
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
    
    # Exchange code for tokens
    try:
        token_data = exchange_code_for_tokens(code, code_verifier)
        
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
async def api_playlists():
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


def main():
    """Main entry point."""
    global config
    config = load_config()
    
    web_config = config.get('web', {})
    host = web_config.get('host', '0.0.0.0')
    port = web_config.get('port', 8081)
    
    # Startup Banner
    print("\n" + "="*50)
    print(f"  Spotify Playlist Manager v{VERSION}")
    print("="*50)
    print(f"  Web Interface   : http://localhost:{port}")
    print(f"  API Endpoint    : http://localhost:{port}/api")
    print(f"  Execution Dir   : {EXECUTION_DIR}")
    print("="*50 + "\n")
    print("Starting web server...")
    
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
