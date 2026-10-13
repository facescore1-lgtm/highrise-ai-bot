#!/bin/bash
set -e

cd /app

PORT="${PORT:-10000}"
PUB_URL="${RENDER_EXTERNAL_URL:-}"

cat > /app/icecast.xml <<EOF
<icecast>
    <location>Earth</location>
    <admin>icemaster@localhost</admin>
    <hostname>localhost</hostname>

    <limits>
        <clients>50</clients>
        <sources>2</sources>
        <queue-size>2097152</queue-size>
        <client-timeout>30</client-timeout>
        <header-timeout>15</header-timeout>
        <source-timeout>10</source-timeout>
        <burst-size>262144</burst-size>
    </limits>

    <authentication>
        <source-password>hackme</source-password>
        <relay-password>hackme</relay-password>
        <admin-user>admin</admin-user>
        <admin-password>hackme</admin-password>
    </authentication>

    <listen-socket>
        <port>${PORT}</port>
    </listen-socket>

    <http-headers>
        <header type="cors" name="Access-Control-Allow-Origin" />
        <header type="cors" name="Access-Control-Allow-Headers" />
        <header type="cors" name="Access-Control-Expose-Headers" />
    </http-headers>

    <paths>
        <logdir>/tmp</logdir>
        <webroot>/usr/share/icecast2/web</webroot>
        <adminroot>/usr/share/icecast2/admin</adminroot>
        <alias source="/" destination="/status.xsl"/>
    </paths>

    <logging>
        <accesslog>access.log</accesslog>
        <errorlog>error.log</errorlog>
        <loglevel>debug</loglevel>
        <logsize>10000</logsize>
    </logging>
</icecast>
EOF

/usr/bin/icecast2 -c /app/icecast.xml &
ICECAST_PID=$!

READY=0
for i in $(seq 1 15); do
    if (echo > "/dev/tcp/127.0.0.1/${PORT}") 2>/dev/null; then
        READY=1
        break
    fi
    sleep 1
done

if [ "${READY}" = "0" ]; then
    echo "[start] HATA: Icecast ${PORT} portunda acilmadi"
    kill ${ICECAST_PID} 2>/dev/null || true
    sleep 1
    exit 1
fi
echo "[start] Icecast ${PORT} portunda dinliyor"

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