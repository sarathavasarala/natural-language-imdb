#!/usr/bin/env python3
"""Synchronize the DuckDB artifact before the web server starts."""

import logging

from app.views import ensure_local_duckdb_database


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


if __name__ == "__main__":
    ensure_local_duckdb_database()
