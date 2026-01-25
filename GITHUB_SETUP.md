# GitHub Repository Setup

## Step 1: Create Repository on GitHub

1. Go to [GitHub.com](https://github.com) and sign in as `simondsmason`
2. Click the **+** icon in the top right corner
3. Select **"New repository"**
4. Fill in the repository details:
   - **Repository name**: `unraid-spotify` (or `spotify-playlist-manager`)
   - **Description**: `Web application for managing Spotify playlists, built with FastAPI`
   - **Visibility**: Choose Public or Private
   - **Initialize with**: ❌ **DO NOT** check "Add a README file" (we already have one)
   - **Add .gitignore**: ❌ **DO NOT** add (we already have one)
   - **Choose a license**: Optional (MIT recommended)
5. Click **"Create repository"**

## Step 2: Connect Local Repository to GitHub

After creating the repository on GitHub, run these commands:

```bash
cd "/Users/simon/Documents/Code Repositories/Unraid-Spotify"
git remote add origin https://github.com/simondsmason/unraid-spotify.git
git branch -M main
git push -u origin main
```

**Note:** Replace `unraid-spotify` with your actual repository name if you chose a different name.

## Step 3: Verify

1. Go to your repository on GitHub: `https://github.com/simondsmason/unraid-spotify`
2. Verify all files are present
3. Check that `spotify_config.json` is **NOT** in the repository (it should be excluded by .gitignore)

## Repository Structure

Your repository should include:
- ✅ `spotify_app.py` - Main application
- ✅ `requirements.txt` - Python dependencies
- ✅ `README.md` - Documentation
- ✅ `DEPLOYMENT.md` - Deployment guide
- ✅ `Dockerfile` - Docker configuration
- ✅ `docker-compose.yml` - Docker Compose configuration
- ✅ `.gitignore` - Git ignore rules
- ✅ `templates/` - Web UI templates
- ✅ `Project - Deployment/` - Deployment scripts
- ❌ `spotify_config.json` - **EXCLUDED** (contains secrets)
- ❌ `spotify_tokens.json` - **EXCLUDED** (auto-generated, contains tokens)

## Future Updates

To push future changes:

```bash
git add .
git commit -m "Description of changes"
git push origin main
```
