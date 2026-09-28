#!/bin/bash
set -e

cd /app

PORT="${PORT:-10000}"
PUB_URL="${RENDER_EXTERNAL_URL:-}"

sed -i "s|<port>8000</port>|<port>${PORT}</port>|" /app/icecast.xml

/usr/bin/icecast2 -c /app/icecast.xml >/tmp/icecast.log 2>&1 &
ICECAST_PID=$!

sleep 2

cat > /app/music_config.json <<EOF
{
  "icecast": {
    "host": "localhost",
    "port": ${PORT},
    "mount": "stream",
    "user": "source",
    "password": "hackme",
    "publicUrl": "${PUB_URL}/stream"
  }
}
EOF

export STREAM_PUBLIC_URL="${PUB_URL}/stream"
echo "[start] Yayin adresi: ${PUB_URL}/stream (port ${PORT})"

exec python -u main.py