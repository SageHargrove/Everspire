#!/usr/bin/env bash
# Redeploy the Everspire world server. Runs ON THE BOX, not locally.
#
#   scp -i "$TOE_KEY" deploy/redeploy_world_server.sh toe_deploy.tgz "$TOE_HOST":/home/ubuntu/
#   ssh -i "$TOE_KEY" "$TOE_HOST" 'bash redeploy_world_server.sh'
#
# Replaces the runbook's inline docker run, which had a live landmine:
#
#     -e ARENA_ADMIN_KEY=$(cat ~/admin_key 2>/dev/null || echo changeme)
#
# ~/admin_key has never existed on this host, so that line would have quietly
# deployed the literal key "changeme" to a public server and handed the season
# reset endpoint to anyone who tried the obvious. This script instead reads the
# key off the RUNNING container, refuses to continue if it can't find one, and
# never invents a fallback.
set -euo pipefail

TARBALL="${1:-/home/ubuntu/toe_deploy.tgz}"
IMAGE=tower-world-server
NAME=world-server

echo "── 1/6  recovering the existing admin key ──"
KEY=""
if sudo docker inspect "$NAME" >/dev/null 2>&1; then
    KEY=$(sudo docker inspect "$NAME" --format '{{range .Config.Env}}{{println .}}{{end}}' \
          | sed -n 's/^ARENA_ADMIN_KEY=//p' | head -1)
fi
if [ -z "$KEY" ] && [ -f ~/admin_key ]; then
    KEY=$(cat ~/admin_key)
fi
if [ -z "$KEY" ]; then
    echo "FATAL: no admin key found (no running container, no ~/admin_key)." >&2
    echo "Refusing to deploy — a guessable admin key is worse than downtime." >&2
    echo "Set one deliberately:  openssl rand -hex 24 > ~/admin_key && chmod 600 ~/admin_key" >&2
    exit 1
fi
# Persist it so a future deploy still works even if the container is gone.
printf '%s' "$KEY" > ~/admin_key
chmod 600 ~/admin_key
echo "    key recovered (${#KEY} chars) and saved to ~/admin_key"

echo "── 2/6  unpacking source ──"
test -f "$TARBALL" || { echo "FATAL: $TARBALL not found" >&2; exit 1; }
rm -rf arena_server backend
tar xzf "$TARBALL"
test -f arena_server/main.py || { echo "FATAL: tarball missing arena_server/main.py" >&2; exit 1; }
test -f backend/services/combat_service.py || { echo "FATAL: tarball missing the shared combat engine" >&2; exit 1; }

echo "── 3/6  building image (context = repo root, needs sibling backend/) ──"
sudo docker build -q -f arena_server/Dockerfile -t "$IMAGE" .

echo "── 4/6  swapping the container ──"
sudo docker rm -f "$NAME" >/dev/null 2>&1 || true
# -p 127.0.0.1:8001:8001 is load-bearing. A bare -p 8001:8001 binds 0.0.0.0 and
# Docker's iptables DNAT rules bypass ufw, exposing the API in cleartext around
# Caddy — its TLS and its rate limiter both.
sudo docker run -d --name "$NAME" --restart unless-stopped \
    -p 127.0.0.1:8001:8001 \
    -e ARENA_ADMIN_KEY="$KEY" \
    -v world_data:/app/data \
    "$IMAGE" >/dev/null

echo "── 5/6  waiting for health ──"
for i in $(seq 1 30); do
    if curl -fsS -m 3 http://127.0.0.1:8001/ >/dev/null 2>&1; then
        echo "    up after ${i}s"
        break
    fi
    sleep 1
    [ "$i" = 30 ] && { echo "FATAL: container did not become healthy" >&2
                       sudo docker logs --tail 40 "$NAME" >&2; exit 1; }
done

echo "── 6/6  verifying exposure + data ──"
echo -n "    accounts preserved: "
sudo docker exec "$NAME" python -c \
  "import sqlite3,os;print(sqlite3.connect(os.environ['ARENA_DB_PATH']).execute('select count(*) from accounts').fetchone()[0])" \
  2>/dev/null || echo "(could not read)"
echo -n "    direct :8001 from outside must FAIL: "
if timeout 5 bash -c "</dev/tcp/$(curl -s -m 5 ifconfig.me)/8001" 2>/dev/null; then
    echo "REACHABLE — THIS IS A PROBLEM"; exit 1
else
    echo "refused (good)"
fi
echo
echo "Deployed. Verify TLS from your machine against the public hostname"
echo "(see deploy/RUNBOOK.local.md, which is gitignored and holds the real host):"
echo "    curl -s \"\$TOE_URL\"/"
