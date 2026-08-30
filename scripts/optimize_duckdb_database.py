#!/usr/bin/env python3
"""Add lookup structures to an existing IMDb DuckDB artifact and upload it."""

import argparse
import logging
import os

import duckdb

from build_duckdb_database import upload_database


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("optimize_duckdb_database")


def optimize_database(database_path):
    connection = duckdb.connect(database_path)
    try:
        connection.execute("CREATE INDEX IF NOT EXISTS titles_id_idx ON titles(title_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS ratings_id_idx ON ratings(title_id)")
        connection.execute("DROP TABLE IF EXISTS crew_lookup")
        logger.info("Creating sorted crew lookup table...")
        connection.execute(
            """
            CREATE TABLE crew_lookup AS
            SELECT person_id, category, title_id
            FROM crew
            ORDER BY person_id, category, title_id
            """
        )
        connection.execute("ANALYZE")
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    logger.info(
        "Optimized %s (%0.1f MiB)",
        database_path,
        os.path.getsize(database_path) / 1024 / 1024,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Optimize and upload an existing IMDb DuckDB database."
    )
    parser.add_argument("--database", default="db/imdb.duckdb")
    parser.add_argument(
        "--connection-string",
        default=os.getenv("AZURE_STORAGE_CONNECTION_STRING"),
    )
    parser.add_argument("--container", default="imdb-data")
    parser.add_argument("--blob-name", default="imdb.duckdb")
    parser.add_argument("--no-upload", action="store_true")
    args = parser.parse_args()

    optimize_database(args.database)
    if not args.no_upload:
        if not args.connection_string:
            parser.error(
                "Set AZURE_STORAGE_CONNECTION_STRING or pass --connection-string."
            )
        upload_database(
            args.connection_string,
            args.container,
            args.database,
            args.blob_name,
        )


if __name__ == "__main__":
    main()
