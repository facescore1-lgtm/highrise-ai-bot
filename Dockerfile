FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ffmpeg \
       icecast2 \
       curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -L -o /usr/local/bin/cloudflared \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    && chmod +x /usr/local/bin/cloudflared

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY deploy/highrise__main__.py /usr/local/lib/python3.12/site-packages/highrise/__main__.py

COPY . .
COPY config.example.json config.json

EXPOSE 8000 8001

CMD ["bash", "start.sh"]
