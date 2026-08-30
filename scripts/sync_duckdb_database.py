#!/usr/bin/env python3
"""Synchronize the DuckDB artifact before the web server starts."""

import logging
import os
import shutil

import app.views as views


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def sync_runtime_database():
    runtime_path = os.path.abspath(views.DUCKDB_DATABASE_PATH)
    cache_path = os.getenv("DUCKDB_CACHE_PATH", "").strip()
    if not cache_path or os.path.abspath(cache_path) == runtime_path:
        return views.ensure_local_duckdb_database()

    cache_path = os.path.abspath(cache_path)
    original_path = views.DUCKDB_DATABASE_PATH
    views.DUCKDB_DATABASE_PATH = cache_path
    try:
        views.ensure_local_duckdb_database()
    finally:
        views.DUCKDB_DATABASE_PATH = original_path

    cache_etag_path = f"{cache_path}.etag"
    runtime_etag_path = f"{runtime_path}.etag"
    with open(cache_etag_path, "r", encoding="utf-8") as etag_file:
        cache_etag = etag_file.read().strip()
    if views._local_database_is_current(runtime_path, cache_etag):
        logging.info("Using current runtime DuckDB database: %s", runtime_path)
        return runtime_path

    os.makedirs(os.path.dirname(runtime_path), exist_ok=True)
    temp_path = f"{runtime_path}.{os.getpid()}.copy"
    temp_etag_path = f"{runtime_etag_path}.{os.getpid()}.copy"
    logging.info("Copying DuckDB database to local runtime storage: %s", runtime_path)
    try:
        shutil.copyfile(cache_path, temp_path)
        shutil.copyfile(cache_etag_path, temp_etag_path)
        os.replace(temp_path, runtime_path)
        os.replace(temp_etag_path, runtime_etag_path)
    finally:
        for partial_path in (temp_path, temp_etag_path):
            if os.path.exists(partial_path):
                os.remove(partial_path)

    logging.info("Runtime DuckDB database is ready at %s", runtime_path)
    return runtime_path


if __name__ == "__main__":
    sync_runtime_database()
