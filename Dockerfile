# IMDb Intelligence - Modern Cloud-Native Container
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# Install system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-install DuckDB Azure and HTTPFS extensions in build stage
RUN python -c "import duckdb; con = duckdb.connect(); con.execute('INSTALL azure; INSTALL httpfs;')"

# Copy application files
COPY . .

EXPOSE 8080

# Synchronize the database before accepting traffic.
CMD python scripts/sync_duckdb_database.py && exec gunicorn --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 120 run:app
