# Base image for Home Assistant add-ons
ARG BUILD_FROM=ghcr.io/hassio-addons/base:14.0.1
FROM ${BUILD_FROM}

LABEL maintainer="smartgeeky@hotmail.com"

# Set working directory
WORKDIR /app

# Install required tools and libraries
RUN apk add --no-cache python3 py3-pip sqlite bash && \
    python3 -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir \
        "flask[async]" \
        feedparser \
        requests \
        beautifulsoup4 \
        lxml \
        websockets \
        gunicorn

# Copy scripts and configurations
COPY run.sh /run.sh
COPY main.py /app/main.py
COPY static /app/static

# Set permissions for startup script
RUN chmod +x /run.sh

# Set media folder as volume
VOLUME /media

ENTRYPOINT [ "/run.sh" ]
