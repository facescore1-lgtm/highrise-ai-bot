#!/bin/bash
set -e
cd /app

PORT="${PORT:-10000}"
ICECAST_PORT="${ICECAST_PORT:-9000}"
CONTROL_PORT="${CONTROL_PORT:-8090}"
PUB_URL="${RENDER_EXTERNAL_URL:-}"
PUB_HOST=$(echo "${PUB_URL}" | sed -E 's|https?://||; s|/.*||')

cat > /app/icecast.xml <<EOF
<icecast>
    <location>Earth</location>
    <admin>icemaster@localhost</admin>
    <hostname>${PUB_HOST:-localhost}</hostname>

    <limits>
        <clients>50</clients>
        <sources>2</sources>
        <queue-size>2097152</queue-size>
        <burst-size>262144</burst-size>
    </limits>

    <authentication>
        <source-password>hackme</source-password>
        <relay-password>hackme</relay-password>
        <admin-user>admin</admin-user>
        <admin-password>hackme</admin-password>
    </authentication>

    <listen-socket>
        <port>${ICECAST_PORT}</port>
    </listen-socket>

    <changeowner>
        <user>nobody</user>
        <group>nogroup</group>
    </changeowner>

    <paths>
        <logdir>/tmp</logdir>
        <webroot>/usr/share/icecast2/web</webroot>
        <adminroot>/usr/share/icecast2/admin</adminroot>
    </paths>
    <alias source="/" destination="/status.xsl"/>
    <alias source="/stream" destination="/stream1"/>
    <fileserve>0</fileserve>

    <logging>
        <accesslog>access.log</accesslog>
        <errorlog>error.log</errorlog>
        <loglevel>3</loglevel>
        <logsize>10000</logsize>
    </logging>
</icecast>
EOF

rm -f /app/icecast.log
setpriv --reuid=nobody --regid=nogroup --clear-groups /usr/bin/icecast2 -c /app/icecast.xml > /app/icecast.log 2>&1 &
ICECAST_PID=$!

READY=0
for i in $(seq 1 20); do
    if (echo > "/dev/tcp/127.0.0.1/${ICECAST_PORT}") 2>/dev/null; then
        READY=1
        break
    fi
    sleep 1
done

if [ "${READY}" = "0" ]; then
    echo "[start] HATA: Icecast ${ICECAST_PORT} portunda acilmadi:"
    cat /app/icecast.log
    kill ${ICECAST_PID} 2>/dev/null || true
    exit 1
fi
echo "[start] Icecast ${ICECAST_PORT} portunda dinliyor"

python - <<'PYEOF'
import json
import os

base = json.load(open("/app/config.render.json", encoding="utf-8"))
ice = base.setdefault("icecast", {})
ice["host"] = "127.0.0.1"
ice["port"] = int(os.environ.get("ICECAST_PORT", "9000"))
ice["mount"] = "/stream1"
pub = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
ice["url"] = (pub + "/stream1") if pub else "http://127.0.0.1:%d/stream1" % ice["port"]
hr = base.setdefault("highrise", {})
if os.environ.get("ROOM_ID"):
    hr["room_id"] = os.environ["ROOM_ID"]
if os.environ.get("API_TOKEN"):
    hr["api_token"] = os.environ["API_TOKEN"]
ctrl = base.setdefault("control", {})
ctrl["http"] = True
ctrl["host"] = "127.0.0.1"
ctrl["port"] = int(os.environ.get("CONTROL_PORT", "8090"))
yt = base.setdefault("youtube", {})
if os.environ.get("COOKIES_FILE"):
    yt["cookies_file"] = os.environ["COOKIES_FILE"]
elif os.environ.get("COOKIES_B64"):
    import base64
    data = base64.b64decode(os.environ["COOKIES_B64"])
    with open("/app/cookies.txt", "wb") as fh:
        fh.write(data)
    yt["cookies_file"] = "/app/cookies.txt"
with open("/app/config.json", "w", encoding="utf-8") as fh:
    json.dump(base, fh, ensure_ascii=False, indent=2)
print("[start] config.json olusturuldu (icecast port %d, kontrol port %d)" % (ice["port"], ctrl["port"]), flush=True)
PYEOF

rm -f /app/gateway.log
nohup python -u /app/gateway.py > /app/gateway.log 2>&1 &

GATEWAY_READY=0
for i in $(seq 1 10); do
    if (echo > "/dev/tcp/127.0.0.1/${PORT}") 2>/dev/null; then
        GATEWAY_READY=1
        break
    fi
    sleep 1
done
if [ "${GATEWAY_READY}" = "0" ]; then
    echo "[start] HATA: gateway ${PORT} portunda acilmadi:"
    cat /app/gateway.log
    exit 1
fi
echo "[start] Gateway ${PORT} portunda dinliyor"
echo "[start] Yayin adresi: ${PUB_URL}/stream1"

exec python -u /app/bot.py --config /app/config.json