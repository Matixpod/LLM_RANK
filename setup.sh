#!/usr/bin/env bash
# LLM-RANK bootstrap script. Idempotent — safe to re-run.
# Installs python3.11, node 20, creates venv, installs backend + frontend deps.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

log()  { printf "\033[1;32m[setup]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[setup]\033[0m %s\n" "$*"; }
err()  { printf "\033[1;31m[setup]\033[0m %s\n" "$*" >&2; }

# --- 1. Python 3.11 ----------------------------------------------------------
if ! command -v python3.11 >/dev/null 2>&1; then
    log "python3.11 not found — installing via apt..."
    sudo apt update
    sudo apt install -y software-properties-common
    # deadsnakes PPA provides python3.11 on Ubuntu versions that don't ship it
    if ! apt-cache show python3.11 >/dev/null 2>&1; then
        sudo add-apt-repository -y ppa:deadsnakes/ppa
        sudo apt update
    fi
    sudo apt install -y python3.11 python3.11-venv python3.11-full python3-pip
else
    log "python3.11 present: $(python3.11 --version)"
fi

if ! command -v python3.11 >/dev/null 2>&1; then
    err "python3.11 install failed. Install manually, then re-run this script."
    exit 1
fi

# --- 2. Node 20 --------------------------------------------------------------
NODE_OK=0
if command -v node >/dev/null 2>&1; then
    NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
    if [ "$NODE_MAJOR" -ge 20 ]; then
        log "node $(node --version) present"
        NODE_OK=1
    fi
fi
if [ "$NODE_OK" -eq 0 ]; then
    log "installing Node 20 from NodeSource..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt install -y nodejs
fi

# --- 3. venv -----------------------------------------------------------------
if [ ! -d "venv" ]; then
    log "creating venv with python3.11..."
    python3.11 -m venv venv
else
    log "venv already exists"
fi

# shellcheck disable=SC1091
source venv/bin/activate

# --- 4. pip upgrade + requirements ------------------------------------------
log "upgrading pip..."
pip install --upgrade pip >/dev/null

log "installing Python requirements..."
pip install -r requirements.txt

# --- 5. frontend -------------------------------------------------------------
log "installing frontend deps..."
pushd frontend >/dev/null
npm install
popd >/dev/null

# --- 6. .env seed ------------------------------------------------------------
if [ ! -f ".env" ]; then
    cp .env.example .env
    warn ".env created from .env.example — fill in real API keys before scanning."
fi

log "✅ Setup complete. Run: source venv/bin/activate && python run.py --help"
