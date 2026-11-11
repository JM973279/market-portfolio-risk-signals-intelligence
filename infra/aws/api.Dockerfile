# Portfolio server image for the AWS Lightsail container service.
# Build from the repository root: docker build -f infra/aws/api.Dockerfile .
# The server is stdlib only, so there is nothing to install.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=3108

WORKDIR /app
COPY qsignals/ qsignals/
COPY data/portfolio/ data/portfolio/
# Historical replay reads the Korean scenario library from here.
COPY frontend/public/data/korea-scenarios.json frontend/public/data/korea-scenarios.json

USER nobody
EXPOSE 3108
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=3)"
CMD ["sh", "-c", "exec python -m qsignals.portfolio_server --host 0.0.0.0 --port \"$PORT\""]
