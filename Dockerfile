FROM python:3.12-slim
WORKDIR /app
COPY server/pyproject.toml ./
COPY server/soccer_wallart ./soccer_wallart
RUN pip install --no-cache-dir .
ENV SOCCER_WALLART_CONFIG=/config/config.yaml
EXPOSE 8080
# Mount a directory containing config.yaml at /config
CMD ["uvicorn", "soccer_wallart.app:app", "--host", "0.0.0.0", "--port", "8080"]
