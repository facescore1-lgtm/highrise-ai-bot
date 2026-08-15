#!/bin/bash
set -e

cd /app

# 1) Icecast
/usr/bin/icecast2 -c /app/icecast.xml &
ICECAST_PID=$!

# 2) cloudflared tünel
/usr/local/bin/cloudflared tunnel --url http://localhost:8000 \
    --logfile /tmp/cloudflared.log --no-autoupdate > /dev/null 2>&1 &
CF_PID=$!

# 3) Tünel adresini bekle
URL=""
for i in $(seq 1 60); do
    URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/cloudflared.log 2>/dev/null | tail -1 || true)
    if [ -n "$URL" ]; then
        break
    fi
    sleep 2
done

if [ -z "$URL" ]; then
    echo "[start] HATA: Tünel adresi alınamadı"
    cat /tmp/cloudflared.log 2>/dev/null || true
    exit 1
fi
echo "[start] Tünel adresi: $URL"

# 4) music_config.json'u tazele (publicUrl + container uyumlu)
cat > /app/music_config.json <<EOF
{
  "icecast": {
    "host": "localhost",
    "port": 8000,
    "mount": "stream",
    "user": "source",
    "password": "hackme",
    "publicUrl": "$URL/stream"
  }
}
EOF

export STREAM_PUBLIC_URL="$URL/stream"

# 5) Bot
exec python -u main.py
