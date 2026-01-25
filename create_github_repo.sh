#!/bin/bash
# Script to create GitHub repository and push code

REPO_NAME="unraid-spotify"
DESCRIPTION="Web application for managing Spotify playlists, built with FastAPI"
USERNAME="simondsmason"

# Check if GitHub token is available
if [ -z "$GITHUB_TOKEN" ]; then
    echo "⚠️  GITHUB_TOKEN environment variable not set."
    echo ""
    echo "To create the repository automatically, you need a GitHub Personal Access Token."
    echo ""
    echo "Option 1: Create repository manually (recommended):"
    echo "1. Go to: https://github.com/new"
    echo "2. Repository name: $REPO_NAME"
    echo "3. Description: $DESCRIPTION"
    echo "4. Choose Public or Private"
    echo "5. DO NOT initialize with README, .gitignore, or license"
    echo "6. Click 'Create repository'"
    echo ""
    echo "Then run these commands:"
    echo "  git remote add origin https://github.com/$USERNAME/$REPO_NAME.git"
    echo "  git push -u origin main"
    echo ""
    echo "Option 2: Create token and run this script again:"
    echo "1. Go to: https://github.com/settings/tokens"
    echo "2. Click 'Generate new token' → 'Generate new token (classic)'"
    echo "3. Give it a name (e.g., 'repo-creation')"
    echo "4. Select scope: 'repo' (full control of private repositories)"
    echo "5. Click 'Generate token'"
    echo "6. Copy the token"
    echo "7. Run: export GITHUB_TOKEN=your_token_here"
    echo "8. Run this script again: ./create_github_repo.sh"
    exit 1
fi

echo "Creating GitHub repository: $REPO_NAME..."

# Create repository via GitHub API
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/user/repos \
  -d "{\"name\":\"$REPO_NAME\",\"description\":\"$DESCRIPTION\",\"private\":false}")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" -eq 201 ]; then
    echo "✅ Repository created successfully!"
    echo ""
    echo "Connecting local repository to GitHub..."
    
    git remote add origin https://github.com/$USERNAME/$REPO_NAME.git 2>/dev/null || \
    git remote set-url origin https://github.com/$USERNAME/$REPO_NAME.git
    
    echo "Pushing code to GitHub..."
    git push -u origin main
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ Success! Repository is now on GitHub:"
        echo "   https://github.com/$USERNAME/$REPO_NAME"
    else
        echo "❌ Push failed. Please check your credentials."
    fi
elif [ "$HTTP_CODE" -eq 422 ]; then
    echo "⚠️  Repository already exists or name is invalid."
    echo "Connecting to existing repository..."
    git remote add origin https://github.com/$USERNAME/$REPO_NAME.git 2>/dev/null || \
    git remote set-url origin https://github.com/$USERNAME/$REPO_NAME.git
    git push -u origin main
else
    echo "❌ Failed to create repository. HTTP code: $HTTP_CODE"
    echo "Response: $BODY"
    exit 1
fi
