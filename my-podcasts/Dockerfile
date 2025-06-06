# Osnovna slika za Home Assistant dodatke
ARG BUILD_FROM=ghcr.io/hassio-addons/base:14.0.1
FROM ${BUILD_FROM}

LABEL maintainer="tvoj-email@domena.com"

# Nastavi delovni imenik
WORKDIR /app

# Namestitev potrebnih orodij in knjižnic
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

# Kopiraj skripte in konfiguracije
COPY run.sh /run.sh
COPY main.py /app/main.py
COPY static /app/static

# Nastavi dovoljenja za zagonsko skripto
RUN chmod +x /run.sh

# Nastavi medijsko mapo kot volumen
VOLUME /media

ENTRYPOINT [ "/run.sh" ]
