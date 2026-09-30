#!/usr/bin/env bash
# Provision the Fog Waste Management web service on a fresh Ubuntu 22.04/24.04 VM.
# Idempotent: safe to re-run to pull the latest code and restart.
#
#   sudo bash setup.sh                 # prompts for ADMIN_API_KEY on first run
#   sudo ADMIN_API_KEY=... bash setup.sh
#
# Optional: REPO_URL, BRANCH (default: main)
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/arnav-pawaskar/WasteManagmentSystem.git}"
BRANCH="${BRANCH:-main}"
APP_DIR=/opt/wms
APP_USER=wms
ENV_FILE=/etc/wms.env

if [[ $EUID -ne 0 ]]; then
    echo "Run as root: sudo bash $0" >&2
    exit 1
fi

echo "==> Installing system packages"
apt-get update -y
apt-get install -y python3 python3-venv git nginx curl

echo "==> Creating service user '$APP_USER'"
if ! id "$APP_USER" &>/dev/null; then
    useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

echo "==> Fetching code into $APP_DIR"
if [[ -d "$APP_DIR/.git" ]]; then
    git -C "$APP_DIR" fetch --depth 1 origin "$BRANCH"
    git -C "$APP_DIR" reset --hard "origin/$BRANCH"
else
    rm -rf "$APP_DIR"
    git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi

echo "==> Installing Python dependencies"
if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
    python3 -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/web/requirements.txt"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> Writing $ENV_FILE"
if [[ ! -f "$ENV_FILE" ]]; then
    key="${ADMIN_API_KEY:-}"
    if [[ -z "$key" ]]; then
        read -r -s -p "Admin API key (leave blank to generate one): " key
        echo
    fi
    if [[ -z "$key" ]]; then
        key="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
        echo "Generated admin key: $key"
        echo "Save it now - it is stored only in $ENV_FILE."
    fi
    umask 077
    printf 'ADMIN_API_KEY=%s\nAUTOSTART=true\n' "$key" > "$ENV_FILE"
    chown root:root "$ENV_FILE"
    chmod 600 "$ENV_FILE"
else
    echo "    exists, leaving it unchanged"
fi

echo "==> Installing systemd unit"
install -m 644 "$APP_DIR/deploy/waste-mgmt.service" /etc/systemd/system/waste-mgmt.service
systemctl daemon-reload
systemctl enable waste-mgmt
systemctl restart waste-mgmt

echo "==> Configuring nginx"
install -m 644 "$APP_DIR/deploy/nginx-wms.conf" /etc/nginx/sites-available/wms
ln -sf /etc/nginx/sites-available/wms /etc/nginx/sites-enabled/wms
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable nginx
systemctl reload nginx || systemctl restart nginx

echo "==> Waiting for the service"
for _ in $(seq 1 20); do
    if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
        break
    fi
    sleep 1
done
curl -fsS http://127.0.0.1/health && echo

ip="$(curl -fsS -H 'Metadata-Flavor: Google' \
    http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip 2>/dev/null || true)"
echo
echo "Done."
echo "  Dashboard: http://${ip:-<EXTERNAL_IP>}/"
echo "  API docs:  http://${ip:-<EXTERNAL_IP>}/docs"
echo "  Logs:      sudo journalctl -u waste-mgmt -f"
