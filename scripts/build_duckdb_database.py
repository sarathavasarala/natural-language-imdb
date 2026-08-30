#!/usr/bin/env python3
"""Build and upload the read-only DuckDB artifact used by the web app."""

import argparse
import logging
import os
import tempfile
import time
from datetime import datetime, timezone

import duckdb
from azure.storage.blob import BlobServiceClient, ContentSettings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("build_duckdb_database")
logging.getLogger("azure").setLevel(logging.WARNING)

TABLES = ("ratings", "titles", "people", "crew", "episodes", "akas")


def build_database(connection_string, container_name, output_path):
    service = BlobServiceClient.from_connection_string(connection_string)
    container = service.get_container_client(container_name)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    if os.path.exists(output_path):
        os.remove(output_path)

    connection = duckdb.connect(output_path)
    connection.execute("SET preserve_insertion_order = false")
    try:
        with tempfile.TemporaryDirectory(prefix="imdb-duckdb-") as temp_dir:
            for table in TABLES:
                parquet_name = f"{table}.parquet"
                parquet_path = os.path.join(temp_dir, parquet_name)
                properties = container.get_blob_client(parquet_name).get_blob_properties()
                logger.info(
                    "Downloading %s (%0.1f MiB)...",
                    parquet_name,
                    properties.size / 1024 / 1024,
                )
                started = time.perf_counter()
                with open(parquet_path, "wb") as parquet_file:
                    container.download_blob(
                        parquet_name,
                        max_concurrency=8,
                    ).readinto(parquet_file)

                connection.execute(
                    f"""
                    CREATE TABLE {table} AS
                    SELECT * FROM read_parquet(?)
                    """,
                    [parquet_path],
                )
                row_count = connection.execute(
                    f"SELECT count(*) FROM {table}"
                ).fetchone()[0]
                os.remove(parquet_path)
                logger.info(
                    "Loaded %s rows into %s in %0.1fs",
                    f"{row_count:,}",
                    table,
                    time.perf_counter() - started,
                )

        logger.info("Creating person lookup indexes...")
        connection.execute("CREATE INDEX people_name_idx ON people(name)")
        connection.execute("CREATE INDEX people_id_idx ON people(person_id)")
        connection.execute("CREATE INDEX titles_id_idx ON titles(title_id)")
        connection.execute("CREATE INDEX ratings_id_idx ON ratings(title_id)")
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

    size = os.path.getsize(output_path)
    logger.info("Built %s (%0.1f MiB)", output_path, size / 1024 / 1024)
    return size


def upload_database(
    connection_string,
    container_name,
    output_path,
    blob_name,
):
    service = BlobServiceClient.from_connection_string(connection_string)
    blob = service.get_blob_client(container=container_name, blob=blob_name)
    logger.info("Uploading %s to %s/%s...", output_path, container_name, blob_name)
    with open(output_path, "rb") as database_file:
        blob.upload_blob(
            database_file,
            overwrite=True,
            max_concurrency=8,
            content_settings=ContentSettings(
                content_type="application/vnd.duckdb",
            ),
            metadata={
                "built_at": datetime.now(timezone.utc).isoformat(),
                "duckdb_version": duckdb.__version__,
            },
        )
    logger.info("Uploaded database artifact with ETag %s", blob.get_blob_properties().etag)


def main():
    parser = argparse.ArgumentParser(
        description="Build a local DuckDB database from the IMDb Parquet blobs."
    )
    parser.add_argument(
        "--connection-string",
        default=os.getenv("AZURE_STORAGE_CONNECTION_STRING"),
        help="Azure Storage connection string",
    )
    parser.add_argument("--container", default="imdb-data")
    parser.add_argument("--output", default="db/imdb.duckdb")
    parser.add_argument("--blob-name", default="imdb.duckdb")
    parser.add_argument("--no-upload", action="store_true")
    args = parser.parse_args()

    if not args.connection_string:
        parser.error(
            "Set AZURE_STORAGE_CONNECTION_STRING or pass --connection-string."
        )

    build_database(args.connection_string, args.container, args.output)
    if not args.no_upload:
        upload_database(
            args.connection_string,
            args.container,
            args.output,
            args.blob_name,
        )


if __name__ == "__main__":
    main()
