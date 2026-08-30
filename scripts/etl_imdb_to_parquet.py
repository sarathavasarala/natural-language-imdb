#!/usr/bin/env python3
"""
IMDb to Parquet ETL & Azure Blob Uploader

Downloads IMDb non-commercial TSV dumps from datasets.imdbws.com,
transforms them into schema-compatible, column-compressed Parquet files,
and uploads them to an Azure Blob Storage container.
"""

import os
import sys
import time
import argparse
import logging
import tempfile
import urllib.request
import duckdb
from azure.storage.blob import BlobServiceClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("imdb_etl")

DATASETS = {
    "ratings": {
        "url": "https://datasets.imdbws.com/title.ratings.tsv.gz",
        "parquet_name": "ratings.parquet",
        "sql": """
            SELECT 
                tconst AS title_id,
                TRY_CAST(averageRating AS DOUBLE) AS rating,
                TRY_CAST(numVotes AS BIGINT) AS votes
            FROM read_csv('{tsv_path}', delim='\t', nullstr='\\N', header=True, quote='')
        """
    },
    "titles": {
        "url": "https://datasets.imdbws.com/title.basics.tsv.gz",
        "parquet_name": "titles.parquet",
        "sql": """
            SELECT 
                tconst AS title_id,
                titleType AS type,
                primaryTitle AS primary_title,
                originalTitle AS original_title,
                NULL::VARCHAR AS original_language,
                NULL::VARCHAR AS origin_country,
                TRY_CAST(isAdult AS INTEGER) AS is_adult,
                TRY_CAST(startYear AS INTEGER) AS premiered,
                TRY_CAST(endYear AS INTEGER) AS ended,
                TRY_CAST(runtimeMinutes AS INTEGER) AS runtime_minutes,
                genres,
                NULL::VARCHAR AS overview,
                NULL::VARCHAR AS poster_path
            FROM read_csv('{tsv_path}', delim='\t', nullstr='\\N', header=True, quote='', ignore_errors=True)
            WHERE titleType IN ('movie', 'tvMovie', 'tvSeries', 'tvMiniSeries', 'tvSpecial')
        """
    },
    "people": {
        "url": "https://datasets.imdbws.com/name.basics.tsv.gz",
        "parquet_name": "people.parquet",
        "sql": """
            SELECT 
                nconst AS person_id,
                primaryName AS name,
                TRY_CAST(birthYear AS INTEGER) AS born,
                TRY_CAST(deathYear AS INTEGER) AS died
            FROM read_csv('{tsv_path}', delim='\t', nullstr='\\N', header=True, quote='', ignore_errors=True)
        """
    },
    "crew": {
        "url": "https://datasets.imdbws.com/title.principals.tsv.gz",
        "parquet_name": "crew.parquet",
        "sql": """
            SELECT 
                tconst AS title_id,
                nconst AS person_id,
                category,
                job,
                characters
            FROM read_csv('{tsv_path}', delim='\t', nullstr='\\N', header=True, quote='', ignore_errors=True)
        """
    },
    "akas": {
        "url": "https://datasets.imdbws.com/title.akas.tsv.gz",
        "parquet_name": "akas.parquet",
        "sql": """
            SELECT 
                titleId AS title_id,
                title,
                region,
                language,
                types,
                attributes,
                TRY_CAST(isOriginalTitle AS INTEGER) AS is_original_title
            FROM read_csv('{tsv_path}', delim='\t', nullstr='\\N', header=True, quote='', ignore_errors=True)
        """
    }
}

def download_file(url: str, dest_path: str):
    logger.info(f"Downloading {url} -> {dest_path}...")
    start_time = time.time()
    
    def reporthook(count, block_size, total_size):
        if count % 2000 == 0 and total_size > 0:
            percent = int(count * block_size * 100 / total_size)
            mb_downloaded = (count * block_size) / (1024 * 1024)
            sys.stdout.write(f"\r  Progress: {percent}% ({mb_downloaded:.1f} MB)")
            sys.stdout.flush()

    urllib.request.urlretrieve(url, dest_path, reporthook=reporthook)
    sys.stdout.write("\n")
    elapsed = time.time() - start_time
    file_size_mb = os.path.getsize(dest_path) / (1024 * 1024)
    logger.info(f"Downloaded {file_size_mb:.1f} MB in {elapsed:.1f}s ({file_size_mb/elapsed:.1f} MB/s)")

def convert_tsv_to_parquet(tsv_path: str, parquet_path: str, sql_template: str):
    logger.info(f"Converting {tsv_path} -> {parquet_path}...")
    start_time = time.time()
    
    con = duckdb.connect()
    query = sql_template.format(tsv_path=tsv_path)
    
    copy_sql = f"""
        COPY ({query}) TO '{parquet_path}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000);
    """
    con.execute(copy_sql)
    con.close()
    
    elapsed = time.time() - start_time
    file_size_mb = os.path.getsize(parquet_path) / (1024 * 1024)
    logger.info(f"Generated {parquet_path} ({file_size_mb:.1f} MB) in {elapsed:.1f}s")

TMDB_MOVIES_DATASET_URL = os.getenv(
    "TMDB_MOVIES_DATASET_URL",
    "https://huggingface.co/datasets/ada-datadruids/full_tmdb_movies_dataset/resolve/main/TMDB_movie_dataset_v11.csv"
)

def process_table(table_key: str, connection_string: str, container_name: str, temp_dir: str, tmdb_url: str = TMDB_MOVIES_DATASET_URL):
    config = DATASETS[table_key]
    tsv_filename = config["url"].split("/")[-1]
    tsv_path = os.path.join(temp_dir, tsv_filename)
    blob_url = f"azure://{container_name}/{config['parquet_name']}"
    tmdb_path = None
    
    try:
        download_file(config["url"], tsv_path)
        
        # Ingest TMDb metadata for titles table if processing titles
        if table_key == "titles" and tmdb_url:
            try:
                tmdb_filename = "tmdb_movies.csv"
                tmdb_path = os.path.join(temp_dir, tmdb_filename)
                logger.info("Downloading TMDb open dataset for language, country, and poster metadata...")
                download_file(tmdb_url, tmdb_path)
            except Exception as e:
                logger.warning(f"Could not download TMDb dataset ({e}). Proceeding with IMDb titles only.")
                tmdb_path = None

        logger.info(f"Transforming & Uploading {tsv_filename} -> {blob_url} via DuckDB...")
        start_time = time.time()
        
        con = duckdb.connect()
        con.execute("INSTALL azure; LOAD azure;")
        con.execute(f"""
            CREATE SECRET IF NOT EXISTS (
                TYPE AZURE,
                CONNECTION_STRING '{connection_string}'
            );
        """)
        
        if table_key == "titles" and tmdb_path and os.path.exists(tmdb_path):
            query = f"""
                SELECT 
                    t.tconst AS title_id,
                    t.titleType AS type,
                    t.primaryTitle AS primary_title,
                    t.originalTitle AS original_title,
                    tmdb.original_language AS original_language,
                    tmdb.origin_country AS origin_country,
                    TRY_CAST(t.isAdult AS INTEGER) AS is_adult,
                    TRY_CAST(t.startYear AS INTEGER) AS premiered,
                    TRY_CAST(t.endYear AS INTEGER) AS ended,
                    TRY_CAST(t.runtimeMinutes AS INTEGER) AS runtime_minutes,
                    t.genres,
                    tmdb.overview AS overview,
                    tmdb.poster_path AS poster_path
                FROM read_csv('{tsv_path}', delim='\t', nullstr='\\N', header=True, quote='', ignore_errors=True) t
                LEFT JOIN (
                    SELECT 
                        imdb_id,
                        original_language,
                        production_countries AS origin_country,
                        overview,
                        poster_path
                    FROM read_csv('{tmdb_path}', header=True, ignore_errors=True, all_varchar=True)
                    WHERE imdb_id IS NOT NULL AND imdb_id != ''
                ) tmdb ON t.tconst = tmdb.imdb_id
                WHERE t.titleType IN ('movie', 'tvMovie', 'tvSeries', 'tvMiniSeries', 'tvSpecial')
            """
        else:
            query = config["sql"].format(tsv_path=tsv_path)

        copy_sql = f"COPY ({query}) TO '{blob_url}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000);"
        con.execute(copy_sql)
        con.close()
        
        elapsed = time.time() - start_time
        logger.info(f"Successfully processed & uploaded {config['parquet_name']} in {elapsed:.1f}s!")
    finally:
        for p in (tsv_path, tmdb_path):
            if p and os.path.exists(p):
                os.remove(p)
        logger.info(f"Cleaned up temporary files for {table_key}.")

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
    parser = argparse.ArgumentParser(description="IMDb TSV to Azure Parquet ETL")
    parser.add_argument("--connection-string", default=get_default_connection_string(),
                        help="Azure Storage Connection String")
    parser.add_argument("--container", default="imdb-data", help="Azure Blob Container Name")
    parser.add_argument("--tables", nargs="+", default=list(DATASETS.keys()),
                        choices=list(DATASETS.keys()), help="Tables to process")
    parser.add_argument("--tmdb-url", default=TMDB_MOVIES_DATASET_URL, help="URL to TMDb open movies CSV/Parquet")
    parser.add_argument("--temp-dir", default=None, help="Custom temporary directory")
    args = parser.parse_args()

    if not args.connection_string:
        logger.error("Missing Azure Storage Connection String. Set AZURE_STORAGE_CONNECTION_STRING or pass --connection-string.")
        sys.exit(1)

    temp_dir = args.temp_dir or tempfile.gettempdir()
    logger.info(f"Starting IMDb ETL pipeline for tables: {args.tables}")
    logger.info(f"Target Azure Blob: container='{args.container}'")
    
    total_start = time.time()
    for table_key in args.tables:
        logger.info(f"\n========================================\nProcessing: {table_key}\n========================================")
        process_table(table_key, args.connection_string, args.container, temp_dir, tmdb_url=args.tmdb_url)
        
    total_elapsed = time.time() - total_start
    logger.info(f"\nETL Pipeline completed successfully in {total_elapsed/60:.2f} minutes!")

if __name__ == "__main__":
    main()
