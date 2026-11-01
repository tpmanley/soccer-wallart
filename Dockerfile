FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SOCCER_WALLART_CONFIG=/config/config.yaml

WORKDIR /app
COPY server/pyproject.toml ./
COPY server/soccer_wallart ./soccer_wallart
RUN pip install .

# /config holds config.yaml (required) and the ESPN response cache (.cache/).
VOLUME /config
EXPOSE 8080

HEALTHCHECK --interval=1m --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4)"

CMD ["uvicorn", "soccer_wallart.app:app", "--host", "0.0.0.0", "--port", "8080"]
