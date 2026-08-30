#!/usr/bin/env python3
"""Build and upload the read-only DuckDB artifact used by the web app."""

import argparse
import logging
import os
import sys
import tempfile
import time
from datetime import datetime, timezone

# Ensure project root is in sys.path for config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import duckdb
from azure.storage.blob import BlobServiceClient, ContentSettings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("build_duckdb_database")
logging.getLogger("azure").setLevel(logging.WARNING)

TABLES = ("ratings", "titles", "people", "crew", "akas")


def build_database(connection_string, container_name, output_path):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    if os.path.exists(output_path):
        os.remove(output_path)

    connection = duckdb.connect(output_path)
    connection.execute("SET preserve_insertion_order = false")
    connection.execute("INSTALL azure; LOAD azure;")
    connection.execute(f"""
        CREATE SECRET IF NOT EXISTS (
            TYPE AZURE,
            CONNECTION_STRING '{connection_string}'
        );
    """)

    for table in TABLES:
        blob_url = f"azure://{container_name}/{table}.parquet"
        logger.info("Loading %s directly from Azure Blob Storage...", blob_url)
        started = time.perf_counter()

        if table in ("crew", "akas"):
            connection.execute(f"""
                CREATE TABLE {table} AS
                SELECT * FROM read_parquet('{blob_url}')
                WHERE title_id IN (SELECT title_id FROM titles)
            """)
        else:
            connection.execute(f"""
                CREATE TABLE {table} AS
                SELECT * FROM read_parquet('{blob_url}')
            """)

        row_count = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        logger.info(
            "Loaded %s rows into %s in %0.1fs",
            f"{row_count:,}",
            table,
            time.perf_counter() - started,
        )

    logger.info("Creating person and title lookup indexes...")
    connection.execute("CREATE INDEX people_name_idx ON people(name)")
    connection.execute("CREATE INDEX people_id_idx ON people(person_id)")
    connection.execute("CREATE INDEX titles_id_idx ON titles(title_id)")
    connection.execute("CREATE INDEX ratings_id_idx ON ratings(title_id)")
    try:
        connection.execute("CREATE INDEX titles_lang_idx ON titles(original_language)")
        connection.execute("CREATE INDEX titles_country_idx ON titles(origin_country)")
    except Exception as e:
        logger.warning("Could not create language/country index: %s", e)

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
    service = BlobServiceClient.from_connection_string(
        connection_string,
        connection_timeout=600,
        read_timeout=600,
    )
    blob = service.get_blob_client(container=container_name, blob=blob_name)
    logger.info("Uploading %s to %s/%s...", output_path, container_name, blob_name)
    file_size = os.path.getsize(output_path)
    with open(output_path, "rb") as database_file:
        blob.upload_blob(
            database_file,
            overwrite=True,
            max_concurrency=4,
            length=file_size,
            timeout=1800,
            content_settings=ContentSettings(
                content_type="application/vnd.duckdb",
            ),
            metadata={
                "built_at": datetime.now(timezone.utc).isoformat(),
                "duckdb_version": duckdb.__version__,
            },
        )
    logger.info("Uploaded database artifact with ETag %s", blob.get_blob_properties().etag)


def get_default_connection_string():
    conn = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not conn:
        try:
            import config
            conn = getattr(config, "AZURE_STORAGE_CONNECTION_STRING", None)
        except Exception:
            pass
    return conn


def main():
    parser = argparse.ArgumentParser(
        description="Build a local DuckDB database from the IMDb Parquet blobs."
    )
    parser.add_argument(
        "--connection-string",
        default=get_default_connection_string(),
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
