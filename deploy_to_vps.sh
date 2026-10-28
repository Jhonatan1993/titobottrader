#!/usr/bin/env bash
set -euo pipefail

if [ -z "${VPS_HOST:-}" ]; then
  echo "Define VPS_HOST (por ejemplo, deploy@mi-vps) antes de desplegar." >&2
  exit 2
fi

TARGET_DIR="${TARGET_DIR:-/opt/titobot}"
case "$TARGET_DIR" in
  /opt/titobot|/root/titobot) ;;
  *) echo "TARGET_DIR solo puede ser /opt/titobot o /root/titobot." >&2; exit 2 ;;
esac
RELEASE_ID="$(date -u +%Y%m%dT%H%M%SZ)"
REMOTE_STAGE="/tmp/titobot-release-$RELEASE_ID"

echo "Preparando release $RELEASE_ID para $VPS_HOST..."
ssh "$VPS_HOST" "mkdir -m 700 '$REMOTE_STAGE'"
rsync -az \
  --exclude='/.git/' \
  --exclude='/venv/' \
  --exclude='/.env' \
  --exclude='/__pycache__/' \
  --exclude='/.pytest_cache/' \
  --exclude='/.agents/' \
  --exclude='/data/broker_config.json' \
  --exclude='/data/trades_history.csv' \
  --exclude='/data/trades_history.json' \
  --exclude='/data/users.db' \
  --exclude='/data/iqoption_risk_state.json' \
  --exclude='/data/.session_secret' \
  --exclude='/data/optimal_params.json' \
  --exclude='/data/security_audit.log' \
  --exclude='/data/ff_calendar.xml' \
  ./ "$VPS_HOST:$REMOTE_STAGE/"

ssh "$VPS_HOST" sudo bash -s -- "$REMOTE_STAGE" "$TARGET_DIR" "$RELEASE_ID" <<'REMOTE'
set -euo pipefail
stage="$1"
target="$2"
release="$3"
case "$target" in
  /opt/titobot)
    archive_root="/opt"
    archive_name="titobot"
    service_user="titobot"
    ;;
  /root/titobot)
    archive_root="/root"
    archive_name="titobot"
    service_user="root"
    ;;
  *)
  echo "Ruta de instalación no permitida." >&2
  exit 2
    ;;
esac
backup_dir="/var/backups/titobot"
backup="$backup_dir/$release.tar.gz"
install -d -m 0700 "$backup_dir"
umask 077
tar --exclude='titobot/.git' --exclude='titobot/venv' -C "$archive_root" -czf "$backup" "$archive_name"
rsync -a "$stage/" "$target/"
chown -R "$service_user:$service_user" "$target"
chmod 0700 "$target/data"
if [ -f "$target/.env" ]; then chmod 0600 "$target/.env"; fi
"$target/venv/bin/pip" install -r "$target/requirements.txt"
systemctl restart titobot

healthy=0
for _ in $(seq 1 12); do
  if curl --silent --fail http://127.0.0.1:5050/healthz >/dev/null; then
    healthy=1
    break
  fi
  sleep 2
done
if [ "$healthy" -ne 1 ]; then
  echo "Health check falló. Snapshot preservado en $backup; servicio requiere revisión manual." >&2
  systemctl --no-pager --full status titobot || true
  exit 1
fi
rm -rf -- "$stage"
echo "Release activo y saludable. Backup: $backup"
REMOTE
