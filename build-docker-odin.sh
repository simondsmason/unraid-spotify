#!/bin/bash
# Build Spotify Playlist Manager Docker image on Odin (Unraid server) via SSH
# This avoids needing Docker Desktop on the Mac

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="${1:-$(git rev-parse --short HEAD 2>/dev/null || echo 'local')}"
IMAGE_NAME="${2:-spotify-playlist-manager}"
TAG="${3:-latest}"
ODIN_IP="${ODIN_IP:-192.168.2.110}"
ODIN_USER="${ODIN_USER:-root}"
BUILD_DIR="/mnt/user/sandbox/spotify-playlist-manager-build"

echo "Building Spotify Playlist Manager Docker image on Odin..."
echo "Version: ${VERSION}"
echo "Image: ${IMAGE_NAME}:${TAG}"
echo ""

# Create build directory in sandbox share on Odin
echo "Creating build directory in sandbox share on Odin..."
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

# Copy source files to Odin
# Create tar file locally first, then copy and extract
TAR_FILE="/tmp/spotify-playlist-manager-build.tar.gz"
echo "Creating archive..."
cd "${SCRIPT_DIR}"
tar czf "${TAR_FILE}" \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.vscode' \
  --exclude='.idea' \
  --exclude='venv' \
  --exclude='env' \
  --exclude='ENV' \
  --exclude='data' \
  --exclude='*.log' \
  --exclude='Project - Deployment/deploy_to_desktop.ps1' \
  --exclude='start_spotify.bat' \
  spotify_app.py \
  requirements.txt \
  Dockerfile \
  .dockerignore \
  templates/ \
  2>/dev/null

echo "Copying archive to Odin..."
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

echo "Extracting archive on Odin..."
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

# Clean up local tar file
rm -f "${TAR_FILE}"

# Build on Odin
echo ""
echo "Building Docker image on Odin (this may take a few minutes)..."
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
    -re "Successfully tagged|error|Error" {
        set output \$expect_out(buffer)
        puts \$output
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

echo ""
echo "Build complete!"
echo "Image: ${IMAGE_NAME}:${TAG}"
echo ""
echo "To deploy, stop and recreate the container on Unraid:"
echo "  docker stop spotify-playlist-manager"
echo "  docker rm spotify-playlist-manager"
echo "  docker run -d --name spotify-playlist-manager --restart unless-stopped -p 8081:8081 -v /mnt/user/appdata/spotify-playlist-manager:/app/data ${IMAGE_NAME}:${TAG}"
