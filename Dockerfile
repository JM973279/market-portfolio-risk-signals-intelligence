FROM python:3.12-slim

WORKDIR /app

# Copy the package and portfolio data (server is stdlib-only)
COPY qsignals/ ./qsignals/
COPY data/portfolio/ ./data/portfolio/

EXPOSE 3108

# Bind to all interfaces so the container is reachable from the host/network
CMD ["python3", "-m", "qsignals.portfolio_server", "--host", "0.0.0.0", "--port", "3108"]
