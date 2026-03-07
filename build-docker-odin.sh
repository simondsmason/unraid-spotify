#!/bin/bash
# Build and deploy Spotify Playlist Manager Docker image on Odin (Unraid server) via SSH
# This avoids needing Docker Desktop on the Mac
#
# Usage:
#   ./build-docker-odin.sh [version] [image-name] [tag]
#   ./build-docker-odin.sh 1.03
#   ./build-docker-odin.sh          # uses git short hash as version

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="${1:-$(git rev-parse --short HEAD 2>/dev/null || echo 'local')}"
IMAGE_NAME="${2:-spotify-playlist-manager}"
TAG="${3:-latest}"
ODIN_IP="${ODIN_IP:-192.168.2.110}"
ODIN_USER="${ODIN_USER:-root}"
BUILD_DIR="/mnt/user/sandbox/spotify-playlist-manager-build"
CONTAINER_NAME="spotify-playlist-manager"

echo "=========================================="
echo "  Build & Deploy: Spotify Playlist Manager"
echo "=========================================="
echo "  Version:   ${VERSION}"
echo "  Image:     ${IMAGE_NAME}:${TAG}"
echo "  Server:    ${ODIN_USER}@${ODIN_IP}"
echo "=========================================="
echo ""

# --- STEP 1: Create build directory ---
echo "[1/5] Creating build directory on Odin..."
expect << EOF
set timeout 30
spawn ssh -o StrictHostKeyChecking=no ${ODIN_USER}@${ODIN_IP} "mkdir -p ${BUILD_DIR}"
expect {
    "password:" { send "#Depeche67\r" }
    "Password:" { send "#Depeche67\r" }
    "(root@${ODIN_IP}) Password:" { send "#Depeche67\r" }
    timeout { puts "Timeout"; exit 1 }
}
expect {
    eof { }
    timeout { exit 1 }
}
EOF

# --- STEP 2: Archive and copy source files ---
echo "[2/5] Archiving and copying source files..."
TAR_FILE="/tmp/spotify-playlist-manager-build.tar.gz"
cd "${SCRIPT_DIR}"
tar czf "${TAR_FILE}" \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.vscode' \
  --exclude='.idea' \
  --exclude='.cursor' \
  --exclude='venv' \
  --exclude='env' \
  --exclude='ENV' \
  --exclude='data' \
  --exclude='backups' \
  --exclude='*.log' \
  --exclude='Project - Deployment/deploy_to_desktop.ps1' \
  --exclude='start_spotify.bat' \
  spotify_app.py \
  requirements.txt \
  Dockerfile \
  .dockerignore \
  templates/ \
  2>/dev/null

expect << SCPEOF
set timeout 300
spawn scp -o StrictHostKeyChecking=no ${TAR_FILE} ${ODIN_USER}@${ODIN_IP}:/mnt/user/sandbox/
expect {
    "password:" { send "#Depeche67\r" }
    "Password:" { send "#Depeche67\r" }
    "(root@${ODIN_IP}) Password:" { send "#Depeche67\r" }
    timeout { puts "Timeout during file copy"; exit 1 }
}
expect {
    eof { }
    timeout { exit 1 }
}
SCPEOF

# --- STEP 3: Extract on server ---
echo "[3/5] Extracting on Odin..."
expect << EXTRACTEOF
set timeout 60
spawn ssh -o StrictHostKeyChecking=no ${ODIN_USER}@${ODIN_IP} "cd /mnt/user/sandbox && tar xzf spotify-playlist-manager-build.tar.gz -C ${BUILD_DIR} && rm -f spotify-playlist-manager-build.tar.gz"
expect {
    "password:" { send "#Depeche67\r" }
    "Password:" { send "#Depeche67\r" }
    "(root@${ODIN_IP}) Password:" { send "#Depeche67\r" }
    timeout { puts "Timeout during extraction"; exit 1 }
}
expect {
    eof { }
    timeout { exit 1 }
}
EXTRACTEOF
rm -f "${TAR_FILE}"

# --- STEP 4: Build Docker image ---
echo "[4/5] Building Docker image on Odin (this may take a few minutes)..."
expect << BUILDEOF
set timeout 1800
spawn ssh -o StrictHostKeyChecking=no ${ODIN_USER}@${ODIN_IP}
expect {
    "password:" { send "#Depeche67\r" }
    "Password:" { send "#Depeche67\r" }
    "(root@${ODIN_IP}) Password:" { send "#Depeche67\r" }
    timeout { puts "Timeout"; exit 1 }
}
expect {
    "# " { send "cd ${BUILD_DIR}\r" }
    "$ " { send "cd ${BUILD_DIR}\r" }
    timeout { exit 1 }
}
expect {
    -re "# |\\$ " {
        send "docker build --tag ${IMAGE_NAME}:${TAG} .\r"
    }
    timeout { exit 1 }
}
expect {
    -re "naming to" {
        set output \$expect_out(buffer)
        puts \$output
    }
    -re "error|Error" {
        puts "BUILD FAILED"
        send "exit\r"
        expect eof
        exit 1
    }
    timeout {
        puts "Build may still be running..."
        puts "Check on server: docker images | grep ${IMAGE_NAME}"
    }
}
expect {
    -re "# |\\$ " {
        send "exit\r"
    }
    timeout { exit 1 }
}
expect eof
BUILDEOF

# --- STEP 5: Deploy (stop old container, start new one) ---
# IMPORTANT: Uses docker rm -f (not docker restart) per Unraid best practice
echo "[5/5] Deploying container..."
expect << 'DEPLOYEOF'
set timeout 60
spawn ssh -o StrictHostKeyChecking=no root@192.168.2.110
expect {
    "password:" { send "#Depeche67\r" }
    "Password:" { send "#Depeche67\r" }
    -re "\\(root@.*\\) Password:" { send "#Depeche67\r" }
    timeout { puts "Timeout"; exit 1 }
}
expect "# "
send "docker rm -f spotify-playlist-manager 2>/dev/null; echo CONTAINER_REMOVED\r"
expect "CONTAINER_REMOVED"
expect "# "
send "docker run -d --name spotify-playlist-manager --restart unless-stopped -p 8100:8081 -v /mnt/user/appdata/spotify-playlist-manager:/app/data -v /mnt/user/media/Audio/spotify-backups:/app/backups -e DATA_DIR=/app/data -e BACKUPS_DIR=/app/backups -e WEB_PORT=8081 --log-driver=syslog --log-opt syslog-address=udp://192.168.2.70:513 --log-opt tag=spotify-playlist-manager --label \"net.unraid.docker.icon=https://developer-assets.spotifycdn.com/images/guidelines/design/icon-framed.svg\" --label \"net.unraid.docker.managed=dockerman\" --label \"net.unraid.docker.webui=http://\[IP\]:\[PORT:8100\]\" --label \"com.spotify-playlist-manager.environment=production\" spotify-playlist-manager:latest && echo DEPLOY_SUCCESS || echo DEPLOY_FAILED\r"
expect {
    "DEPLOY_SUCCESS" { }
    "DEPLOY_FAILED" {
        puts "DEPLOYMENT FAILED"
        send "exit\r"
        expect eof
        exit 1
    }
    timeout {
        puts "Timeout waiting for container start"
        send "exit\r"
        expect eof
        exit 1
    }
}
expect "# "
send "sleep 4\r"
expect "# "
send "docker logs spotify-playlist-manager 2>&1 | tail -3\r"
expect "# "
send "docker ps --filter name=spotify-playlist-manager --format 'STATUS: {{.Status}}'\r"
expect "# "
send "exit\r"
expect eof
DEPLOYEOF

echo ""
echo "=========================================="
echo "  Deploy complete!"
echo "  Image:     ${IMAGE_NAME}:${TAG}"
echo "  Version:   ${VERSION}"
echo "  Container: ${CONTAINER_NAME}"
echo "=========================================="
