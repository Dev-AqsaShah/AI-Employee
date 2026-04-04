#!/usr/bin/env bash
# =============================================================================
# deploy_cloud.sh — One-time Oracle/AWS cloud VM setup (Platinum Tier)
# =============================================================================
# Usage:
#   1. SSH into your cloud VM:  ssh -i ai-key.pem ubuntu@<your-vm-ip>
#   2. Clone repo:              git clone https://github.com/Dev-AqsaShah/AI-Employee
#   3. cd AI-Employee
#   4. Run:                     bash scripts/deploy_cloud.sh
#
# What this does:
#   - Installs Python 3.12, Git, Docker, Chrome
#   - Creates Python venv + installs requirements
#   - Installs Playwright chromium
#   - Copies .env.cloud to .env (you fill in credentials)
#   - Installs systemd services for auto-start
#   - Sets up Git SSH key for vault sync
#   - Starts cloud orchestrator + vault sync
#
# Security:
#   - Never uploads .env, credentials/, or tokens to this script
#   - You must manually copy your Gmail credentials to the cloud VM
# =============================================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
USER_HOME="${HOME}"
PYTHON_MIN="3.10"

echo "=========================================="
echo " AI Employee Cloud Setup (Platinum Tier)"
echo " Repo: ${REPO_DIR}"
echo "=========================================="

# ── System packages ─────────────────────────────────────────────────────────

echo "[1/8] Updating system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-pip python3-venv \
    git curl wget unzip \
    chromium-browser \
    docker.io docker-compose \
    jq htop

# Enable Docker for current user
sudo usermod -aG docker "${USER}" || true

# ── Python venv ──────────────────────────────────────────────────────────────

echo "[2/8] Setting up Python virtual environment..."
cd "${REPO_DIR}"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "[OK] Python venv ready"

# ── Playwright browsers ──────────────────────────────────────────────────────

echo "[3/8] Installing Playwright browsers..."
python -m playwright install chromium --with-deps
echo "[OK] Playwright chromium installed"

# ── Environment file ─────────────────────────────────────────────────────────

echo "[4/8] Setting up .env..."
if [ ! -f "${REPO_DIR}/.env" ]; then
    if [ -f "${REPO_DIR}/.env.cloud.example" ]; then
        cp "${REPO_DIR}/.env.cloud.example" "${REPO_DIR}/.env"
        echo "[WARN] .env created from .env.cloud.example — fill in your credentials!"
    else
        echo "[ERROR] No .env or .env.cloud.example found — create .env manually"
    fi
else
    echo "[OK] .env already exists"
fi

# ── Git SSH setup (for vault sync) ───────────────────────────────────────────

echo "[5/8] Checking Git SSH..."
SSH_KEY="${USER_HOME}/.ssh/id_ed25519"
if [ ! -f "${SSH_KEY}" ]; then
    echo "Generating SSH key for vault sync..."
    ssh-keygen -t ed25519 -C "ai-employee-cloud@$(hostname)" -f "${SSH_KEY}" -N ""
    echo ""
    echo "=========================================="
    echo " Add this SSH public key to GitHub:"
    echo " Settings -> SSH and GPG keys -> New SSH key"
    echo "=========================================="
    cat "${SSH_KEY}.pub"
    echo "=========================================="
    echo "Press ENTER after adding the key to GitHub..."
    read -r
fi

# Test GitHub SSH
if ssh -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
    echo "[OK] GitHub SSH auth working"
else
    echo "[WARN] GitHub SSH auth may not be set up — vault sync via HTTPS will be used"
fi

# ── Systemd services ─────────────────────────────────────────────────────────

echo "[6/8] Installing systemd services..."

# Update WorkingDirectory in service files to match actual path
sed "s|/home/ubuntu/AI-Employee|${REPO_DIR}|g" \
    "${REPO_DIR}/systemd/ai-employee-cloud.service" \
    | sed "s|User=ubuntu|User=${USER}|g" \
    > /tmp/ai-employee-cloud.service

sed "s|/home/ubuntu/AI-Employee|${REPO_DIR}|g" \
    "${REPO_DIR}/systemd/ai-employee-vault-sync.service" \
    | sed "s|User=ubuntu|User=${USER}|g" \
    > /tmp/ai-employee-vault-sync.service

sudo cp /tmp/ai-employee-cloud.service      /etc/systemd/system/
sudo cp /tmp/ai-employee-vault-sync.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable ai-employee-cloud
sudo systemctl enable ai-employee-vault-sync
echo "[OK] Systemd services installed and enabled"

# ── Odoo (optional — Gold Tier Accounting) ───────────────────────────────────

echo "[7/8] Starting Odoo + PostgreSQL (Gold Tier accounting)..."
cd "${REPO_DIR}"
if command -v docker-compose &>/dev/null; then
    docker-compose up -d
    echo "[OK] Odoo starting at http://localhost:8069"
    echo "     Wait ~60s then open http://<your-vm-ip>:8069 to create database"
    echo "     Database name: odoo | Master password: admin123"
else
    echo "[SKIP] docker-compose not found — skipping Odoo"
fi

# ── Start services ───────────────────────────────────────────────────────────

echo "[8/8] Starting AI Employee cloud services..."
sudo systemctl start ai-employee-vault-sync
sleep 3
sudo systemctl start ai-employee-cloud
sleep 3

echo ""
echo "=========================================="
echo " Cloud Setup Complete!"
echo "=========================================="
echo " Services:"
echo "   systemctl status ai-employee-cloud"
echo "   systemctl status ai-employee-vault-sync"
echo ""
echo " Logs:"
echo "   journalctl -u ai-employee-cloud -f"
echo "   journalctl -u ai-employee-vault-sync -f"
echo ""
echo " Odoo Dashboard:"
echo "   http://$(curl -s ifconfig.me 2>/dev/null || echo '<your-vm-ip>'):8069"
echo ""
echo " IMPORTANT NEXT STEPS:"
echo "   1. Fill in credentials in .env"
echo "   2. Copy Gmail credentials: scp credentials/gmail_credentials.json ubuntu@<ip>:~/AI-Employee/credentials/"
echo "   3. Test: python cloud_orchestrator.py --dry-run"
echo "=========================================="
