from flask import Blueprint, render_template, request, jsonify, has_request_context, Response, stream_with_context
import os
import sqlite3
import logging
import json
import time
import re
import threading
import fcntl
import shutil
from openai import AzureOpenAI, OpenAI
import sys
from datetime import datetime
from types import SimpleNamespace
import uuid
import duckdb
from azure.storage.blob import BlobServiceClient

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure comprehensive logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

try:
    from config import (
        AZURE_OPENAI_API_KEY,
        AZURE_OPENAI_API_VERSION,
        AZURE_OPENAI_ENDPOINT,
        AZURE_OPENAI_MODEL,
        AZURE_STORAGE_CONNECTION_STRING,
        AZURE_STORAGE_CONTAINER_NAME,
        DATABASE_PATH
    )
except ImportError:
    logger.info("config.py not found, reading settings from environment variables.")
    AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
    AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
    AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    AZURE_OPENAI_MODEL = os.getenv("AZURE_OPENAI_MODEL", "gpt-5.4")
    AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "imdb-data")
    DATABASE_PATH = os.getenv("DATABASE_PATH", "db/imdb.db")

# Initialize the Flask Blueprint
main = Blueprint('main', __name__)

DB_SCHEMA_PROMPT = """
DATABASE SCHEMA:
- people: person_id (VARCHAR), name (VARCHAR), born (INTEGER), died (INTEGER)
- titles: title_id (VARCHAR), type (VARCHAR: 'movie', 'tvMovie', 'tvSeries', 'tvMiniSeries', 'tvSpecial'), primary_title (VARCHAR), original_title (VARCHAR), original_language (VARCHAR: 2-letter ISO 639-1 code e.g. 'en', 'es', 'fr', 'de', 'ja', 'ko', 'it', 'zh', 'hi', 'te', 'ta', 'ml', 'kn', 'pt', 'ru', 'ar', 'sv', 'nl', 'tr', 'pl', etc.), origin_country (VARCHAR: 2-letter ISO 3166-1 country code e.g. 'US', 'GB', 'IN', 'KR', 'JP', 'FR', 'DE', 'IT', 'CA', 'AU', 'ES', 'MX', 'BR', 'CN', 'SE', 'DK', etc.), is_adult (INTEGER), premiered (INTEGER), ended (INTEGER), runtime_minutes (INTEGER), genres (VARCHAR), overview (VARCHAR: plot synopsis), poster_path (VARCHAR)
- akas: title_id (VARCHAR), title (VARCHAR), region (VARCHAR), language (VARCHAR), types (VARCHAR), attributes (VARCHAR), is_original_title (INTEGER)
- crew: title_id (VARCHAR), person_id (VARCHAR), category (VARCHAR), job (VARCHAR), characters (VARCHAR)
- crew_lookup: person_id (VARCHAR), category (VARCHAR), title_id (VARCHAR), sorted for fast person-credit lookups
- ratings: title_id (VARCHAR), rating (REAL), votes (INTEGER)
"""

def get_azure_credentials(req=None):
    """
    Extracts Azure OpenAI credentials from request headers/body (e.g. from UI localStorage)
    or falls back to server environment/config.py variables.
    """
    api_key = (AZURE_OPENAI_API_KEY or "").strip()
    endpoint = (AZURE_OPENAI_ENDPOINT or "").strip()
    api_version = (AZURE_OPENAI_API_VERSION or "2025-04-01-preview").strip()
    model = (AZURE_OPENAI_MODEL or "gpt-5.4").strip()
    is_custom = False

    if req is not None:
        # Check Custom Request Headers from UI
        h_key = req.headers.get("X-Azure-API-Key")
        h_endpoint = req.headers.get("X-Azure-Endpoint")
        h_version = req.headers.get("X-Azure-API-Version")
        h_model = req.headers.get("X-Azure-Model")

        if h_key and h_key.strip():
            api_key = h_key.strip()
            is_custom = True
        if h_endpoint and h_endpoint.strip():
            endpoint = h_endpoint.strip()
        if h_version and h_version.strip():
            api_version = h_version.strip()
        if h_model and h_model.strip():
            model = h_model.strip()

        # Check JSON payload
        if req.is_json:
            body = req.get_json(silent=True) or {}
            if not h_key and body.get("api_key"):
                api_key = body.get("api_key").strip()
                is_custom = True
            if not h_endpoint and body.get("endpoint"):
                endpoint = body.get("endpoint").strip()
            if not h_version and body.get("api_version"):
                api_version = body.get("api_version").strip()
            if not h_model and body.get("model"):
                model = body.get("model").strip()

    return {
        "api_key": api_key,
        "endpoint": endpoint,
        "api_version": api_version,
        "model": model,
        "is_custom": is_custom
    }

def get_azure_client(creds=None):
    """
    Returns the AI client (OpenAI v1 router or AzureOpenAI) and model name initialized with given credentials.
    Automatically detects and handles:
    - Azure AI Foundry endpoints (e.g. https://<resource>.services.ai.azure.com/openai/v1 or root)
    - Azure AI Model inference endpoints (/models or /v1)
    - Classic Azure OpenAI endpoints (e.g. https://<resource>.openai.azure.com)
    """
    if creds is None:
        creds = get_azure_credentials(request if has_request_context() else None)
    
    api_key = (creds.get("api_key") or "").strip()
    endpoint = (creds.get("endpoint") or "").strip().rstrip("/")
    api_version = (creds.get("api_version") or "2025-04-01-preview").strip()
    model = (creds.get("model") or "gpt-5.6-luna").strip()
    
    if not api_key or not endpoint:
        raise ValueError("AI API Key or Endpoint is not configured. Please set it in config.py or in the UI settings.")

    masked_key = f"{api_key[:4]}...{api_key[-4:]} (length={len(api_key)})" if len(api_key) > 8 else "***"
    logger.info(f"AI Connection Details -> Endpoint: {endpoint} | Model: {model} | API Key: {masked_key}")

    # 1. Direct Foundry / OpenAI-compatible v1 router
    if "/openai/v1" in endpoint or "/v1" in endpoint or "/models" in endpoint:
        logger.info(f"Connecting via OpenAI v1 router to Foundry endpoint: {endpoint}")
        client = OpenAI(
            base_url=endpoint,
            api_key=api_key
        )
        client._azure_creds = creds
        return client, model

    # 2. Foundry domain without /openai/v1 suffix
    if "services.ai.azure.com" in endpoint:
        foundry_v1_url = f"{endpoint}/openai/v1"
        logger.info(f"Connecting via Foundry services.ai.azure.com router: {foundry_v1_url}")
        client = OpenAI(
            base_url=foundry_v1_url,
            api_key=api_key
        )
        client._azure_creds = creds
        return client, model

    # 3. Classic Azure OpenAI (.openai.azure.com or .cognitiveservices.azure.com)
    clean_endpoint = re.sub(r'/openai.*$', '', endpoint)
    logger.info(f"Connecting via AzureOpenAI client to endpoint: {clean_endpoint}")
    client = AzureOpenAI(
        azure_endpoint=clean_endpoint,
        api_version=api_version,
        api_key=api_key
    )
    client._azure_creds = creds
    return client, model

# Thread-safe DuckDB Connection Manager
_duckdb_lock = threading.Lock()
_duckdb_con = None
DUCKDB_BLOB_NAME = os.getenv("DUCKDB_BLOB_NAME", "imdb.duckdb")
DUCKDB_DATABASE_PATH = os.getenv(
    "DUCKDB_DATABASE_PATH",
    "/home/data/imdb.duckdb" if os.getenv("WEBSITE_SITE_NAME") else "db/imdb.duckdb"
)
DUCKDB_QUERY_TIMEOUT = float(os.getenv("DUCKDB_QUERY_TIMEOUT", "30.0"))

def _local_database_is_current(database_path, etag):
    etag_path = f"{database_path}.etag"
    if not os.path.exists(database_path):
        return False
    if os.path.getsize(database_path) > 1_000_000_000:
        if not os.path.exists(etag_path):
            try:
                with open(etag_path, "w", encoding="utf-8") as f:
                    f.write(etag)
            except Exception:
                pass
            return True
        with open(etag_path, "r", encoding="utf-8") as etag_file:
            return etag_file.read().strip() == etag
    return False


def ensure_local_duckdb_database():
    """Download the immutable DuckDB artifact to persistent local storage when needed."""
    database_path = os.path.abspath(DUCKDB_DATABASE_PATH)

    # In local development, use existing database file immediately without remote network checks
    if os.path.exists(database_path) and os.path.getsize(database_path) > 1_000_000_000:
        if not os.getenv("WEBSITE_SITE_NAME"):
            logger.info("Using existing local DuckDB database: %s", database_path)
            return database_path

    if not AZURE_STORAGE_CONNECTION_STRING:
        if os.path.exists(database_path):
            return database_path
        raise RuntimeError(
            f"DuckDB database not found at {database_path} and Azure storage is not configured."
        )

    os.makedirs(os.path.dirname(database_path), exist_ok=True)
    lock_path = f"{database_path}.lock"
    container = AZURE_STORAGE_CONTAINER_NAME or "imdb-data"
    blob_client = BlobServiceClient.from_connection_string(
        AZURE_STORAGE_CONNECTION_STRING
    ).get_blob_client(container=container, blob=DUCKDB_BLOB_NAME)

    with open(lock_path, "a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        properties = blob_client.get_blob_properties()
        etag = properties.etag.strip('"')
        if _local_database_is_current(database_path, etag):
            logger.info("Using current local DuckDB database: %s", database_path)
            return database_path

        temp_path = f"{database_path}.{os.getpid()}.download"
        temp_etag_path = f"{database_path}.etag.{os.getpid()}.download"
        free_bytes = shutil.disk_usage(os.path.dirname(database_path)).free
        if os.path.exists(database_path) and free_bytes < properties.size * 1.1:
            logger.info("Removing stale database before download due to limited disk space.")
            os.remove(database_path)
            if os.path.exists(f"{database_path}.etag"):
                os.remove(f"{database_path}.etag")
        logger.info(
            "Downloading DuckDB database artifact %s/%s (%0.1f MiB)...",
            container,
            DUCKDB_BLOB_NAME,
            properties.size / 1024 / 1024,
        )
        try:
            with open(temp_path, "wb") as database_file:
                blob_client.download_blob(max_concurrency=4).readinto(database_file)
                database_file.flush()
                os.fsync(database_file.fileno())
            with open(temp_etag_path, "w", encoding="utf-8") as etag_file:
                etag_file.write(etag)
                etag_file.flush()
                os.fsync(etag_file.fileno())
            os.replace(temp_path, database_path)
            os.replace(temp_etag_path, f"{database_path}.etag")
        finally:
            for partial_path in (temp_path, temp_etag_path):
                if os.path.exists(partial_path):
                    os.remove(partial_path)

        logger.info("DuckDB database is ready at %s", database_path)
        return database_path


def get_duckdb_database():
    """Get a read-only connection to the local DuckDB database artifact."""
    global _duckdb_con
    with _duckdb_lock:
        if _duckdb_con is None:
            database_path = ensure_local_duckdb_database()
            logger.info("Opening local DuckDB database: %s", database_path)
            _duckdb_con = duckdb.connect(database=database_path, read_only=True)
            try:
                _duckdb_con.execute("SET max_memory = '1.2GB'")
                _duckdb_con.execute("SET threads = 4")
            except Exception as e:
                logger.warning(f"Could not apply DuckDB runtime pragmas: {e}")
        return _duckdb_con.cursor()

def get_database_connection():
    """Get a database connection (DuckDB Azure Parquet or local SQLite fallback)"""
    if AZURE_STORAGE_CONNECTION_STRING:
        return get_duckdb_database()
    
    # Fallback to local SQLite if configured
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), DATABASE_PATH or 'db/imdb.db')
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    # Fallback to DuckDB
    return get_duckdb_database()

def execute_sql_query(sql_query, max_rows=1000, timeout_seconds=DUCKDB_QUERY_TIMEOUT):
    """Execute SQL query and return results with column names, protected by row bounds and timeouts."""
    cursor = None
    timer = None
    try:
        logger.info(f"Executing SQL: {sql_query[:200]}...")
        cursor = get_database_connection()
        
        # Arm execution timeout watchdog for DuckDB cursors
        if timeout_seconds and hasattr(cursor, 'interrupt'):
            timer = threading.Timer(timeout_seconds, cursor.interrupt)
            timer.daemon = True
            timer.start()

        cursor.execute(sql_query)
        
        # Get column names
        column_names = [description[0] for description in cursor.description] if cursor.description else []
        
        # Fetch results with a hard row ceiling to prevent Python heap OOM
        results = cursor.fetchmany(max_rows)
        logger.info(f"Query executed successfully, returned {len(results)} rows (capped at {max_rows})")
        
        return results, column_names
        
    except Exception as e:
        if "interrupt" in str(e).lower() or type(e).__name__ == "InterruptException":
            logger.error(f"SQL execution timed out after {timeout_seconds}s: {sql_query[:150]}")
            raise TimeoutError(f"Query execution timed out after {timeout_seconds} seconds.") from e
        logger.error(f"SQL execution error: {str(e)}")
        raise
    finally:
        if timer:
            timer.cancel()
        if cursor and isinstance(cursor, sqlite3.Connection):
            cursor.close()

def fix_single_quotes_in_sql(sql_query):
    """Safely escape unescaped apostrophes inside words in SQL string literals without corrupting multi-clause queries."""
    if not sql_query:
        return sql_query
    try:
        # Replace unescaped word apostrophes like O'Brien -> O''Brien without swallowing subsequent SQL clauses
        return re.sub(r"(?<=[a-zA-Z])'(?=[a-zA-Z])", "''", sql_query)
    except Exception as e:
        logger.warning(f"Error in SQL quote fixing: {str(e)}, returning original query")
        return sql_query


_has_tmdb_columns = None

def _check_tmdb_columns_available():
    global _has_tmdb_columns, _duckdb_con
    if _has_tmdb_columns is not None:
        return _has_tmdb_columns
    if _duckdb_con is None:
        return False
    try:
        cols = [c[0] for c in _duckdb_con.execute("DESCRIBE titles").fetchall()]
        _has_tmdb_columns = ("original_language" in cols)
    except Exception:
        _has_tmdb_columns = False
    return _has_tmdb_columns


COUNTRY_CODE_MAP = {
    'IN': 'India',
    'FR': 'France',
    'JP': 'Japan',
    'KR': 'South Korea',
    'MX': 'Mexico',
    'CA': 'Canada',
    'DE': 'Germany',
    'IT': 'Italy',
    'ES': 'Spain',
    'GB': 'United Kingdom',
    'UK': 'United Kingdom',
    'US': 'United States'
}

def optimize_generated_sql(sql_query):
    """Route ordinary credit joins through lookup table, expand country filters, and ensure optimal execution plans."""
    if not sql_query:
        return sql_query
    
    # 1. Route crew joins to crew_lookup unless job/characters detail is requested
    if not re.search(r"\b(?:job|characters)\b", sql_query, flags=re.IGNORECASE):
        sql_query = re.sub(
            r"\b(FROM|JOIN)\s+crew\b",
            r"\1 crew_lookup",
            sql_query,
            flags=re.IGNORECASE,
        )

    # 2. Normalize country code / name filters to cover both TMDb country strings and ISO codes
    for code, country_name in COUNTRY_CODE_MAP.items():
        # Match pattern: origin_country = 'IN' or t.origin_country = 'IN'
        pattern = rf"\b(\w+\.)?origin_country\s*=\s*'{code}'"
        replacement = rf"(\1origin_country LIKE '%{country_name}%' OR \1origin_country = '{code}')"
        sql_query = re.sub(pattern, replacement, sql_query, flags=re.IGNORECASE)

    # 3. If running against an existing database artifact that lacks original_language / origin_country columns,
    # translate them to backward-compatible akas lookups so EXPLAIN validation never fails.
    if not _check_tmdb_columns_available():
        sql_query = re.sub(
            r"\b(\w+)\.original_language\s*=\s*'([^']+)'",
            lambda m: f"EXISTS (SELECT 1 FROM akas _ak WHERE _ak.title_id = {m.group(1)}.title_id AND lower(_ak.language) = lower('{m.group(2)}') )",
            sql_query,
            flags=re.IGNORECASE
        )
        sql_query = re.sub(
            r"\b(\w+)\.origin_country\s*=\s*'([^']+)'",
            lambda m: f"EXISTS (SELECT 1 FROM akas _ak WHERE _ak.title_id = {m.group(1)}.title_id AND _ak.region = '{m.group(2)}' )",
            sql_query,
            flags=re.IGNORECASE
        )

    # 4. For yearly/temporal aggregations, ensure NULL release years are excluded
    if re.search(r"\bGROUP\s+BY\s+.*?\b(?:premiered|year)\b", sql_query, flags=re.IGNORECASE):
        if not re.search(r"\bpremiered\s+IS\s+NOT\s+NULL\b", sql_query, flags=re.IGNORECASE):
            if re.search(r"\bWHERE\b", sql_query, flags=re.IGNORECASE):
                sql_query = re.sub(r"\bWHERE\b", "WHERE t.premiered IS NOT NULL AND", sql_query, count=1, flags=re.IGNORECASE)

    return sql_query


def classify_query_result(column_names, results, sql_query=""):
    """
    Classifies a query result into:
    - 'AGGREGATION_SERIES': grouped analytical data (e.g. yearly trend, genre breakdown)
    - 'AGGREGATION_SCALAR': single aggregate metric (e.g. total_movies: 12)
    - 'TITLE_DISCOVERY': standard list of cinema titles
    """
    cols_lower = [c.lower() for c in column_names] if column_names else []
    
    # Check if this query is an ordinary title discovery query
    is_title_query = ('title_id' in cols_lower and 'primary_title' in cols_lower)
    
    # Indicators of aggregate metrics
    metric_cols = [c for c in cols_lower if any(m in c for m in ['count', 'avg', 'sum', 'min', 'max', 'total'])]
    has_group_by = bool(re.search(r'\bGROUP\s+BY\b', sql_query or '', re.IGNORECASE))
    
    if not is_title_query and (metric_cols or has_group_by):
        if len(results) == 1 and len(column_names) == 1:
            return "AGGREGATION_SCALAR"
        elif len(results) >= 1:
            return "AGGREGATION_SERIES"
            
    # Also check single scalar row without group by (e.g. SELECT COUNT(DISTINCT ...) AS total_movies)
    if not is_title_query and len(results) == 1 and (metric_cols or len(column_names) <= 2):
        return "AGGREGATION_SCALAR"

    return "TITLE_DISCOVERY"


def derive_detail_sql(sql_query):
    """
    Given an aggregate query, derives the companion detail SQL to fetch the underlying titles,
    allowing zero-latency drilldown on the frontend.
    """
    if not sql_query:
        return None
    try:
        clean_sql = sql_query.strip().rstrip(';')
        
        # Track parentheses depth to find the top-level SELECT
        depth = 0
        main_select_pos = -1
        for i, char in enumerate(clean_sql):
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
            elif depth == 0 and clean_sql[i:i+6].upper() == 'SELECT' and (i == 0 or clean_sql[i-1].isspace()):
                main_select_pos = i
                
        if main_select_pos == -1:
            return None
            
        cte_part = clean_sql[:main_select_pos].strip()
        main_part = clean_sql[main_select_pos:].strip()
        
        # In main_part, extract the FROM clause up to GROUP BY, ORDER BY, HAVING, or LIMIT
        m = re.search(r'\bFROM\b([\s\S]+?)(?:\bGROUP\s+BY\b|\bORDER\s+BY\b|\bHAVING\b|\bLIMIT\b|$)', main_part, re.IGNORECASE)
        if not m:
            return None
            
        from_clause = m.group(1).strip()
        
        # Check if 'titles' is referenced
        if not re.search(r'\btitles\b', from_clause, re.IGNORECASE):
            return None
            
        # Check if ratings is joined
        has_ratings = bool(re.search(r'\b(?:JOIN|FROM)\s+ratings\b', from_clause, re.IGNORECASE))
        if not has_ratings and re.search(r'\btitles\s+t\b', from_clause, re.IGNORECASE):
            where_m = re.search(r'\bWHERE\b', from_clause, re.IGNORECASE)
            if where_m:
                from_clause = from_clause[:where_m.start()] + ' LEFT JOIN ratings r ON r.title_id = t.title_id ' + from_clause[where_m.start():]
            else:
                from_clause = from_clause + ' LEFT JOIN ratings r ON r.title_id = t.title_id'
                
        detail_select = 'SELECT DISTINCT t.title_id, t.primary_title, t.premiered, t.genres, r.rating, r.votes, t.poster_path'
        order_clause = 'ORDER BY r.votes DESC NULLS LAST, r.rating DESC NULLS LAST, t.premiered DESC NULLS LAST LIMIT 500'
        
        prefix = (cte_part + '\n') if cte_part else ''
        detail_sql = f"{prefix}{detail_select}\nFROM {from_clause}\n{order_clause};"
        return optimize_generated_sql(detail_sql)
    except Exception as e:
        logger.warning(f"Could not derive detail SQL: {e}")
        return None


def validate_sql_query(sql_query, timeout_seconds=8.0):
    """Validation of SQL query for security, isolation, and syntax."""
    if not sql_query or not isinstance(sql_query, str):
        return False

    try:
        sql_clean = sql_query.strip()
        sql_lower = sql_clean.lower()
        
        # Reject dangerous DDL, DML, and database control statements
        dangerous_patterns = [
            'drop', 'delete', 'update', 'insert', 'alter', 'create', 'truncate',
            'attach', 'detach', 'copy', 'export', 'import', 'pragma', 'call', 'install', 'load'
        ]
        for pattern in dangerous_patterns:
            if re.search(r'\b' + pattern + r'\b', sql_lower):
                logger.warning(f"Potentially dangerous SQL operation detected: {pattern}")
                return False
        
        # Enforce read-only SELECT or WITH statement
        if not sql_lower.startswith('select') and not sql_lower.startswith('with'):
            logger.warning("SQL query must be a SELECT or WITH statement")
            return False
            
        # Reject semicolon-chained multiple statements
        stripped_no_semi = sql_clean.rstrip(';').strip()
        if ';' in stripped_no_semi:
            logger.warning("Multiple SQL statements separated by semicolon are disallowed")
            return False
        
        # Syntax validation using EXPLAIN with timeout protection
        cursor = get_database_connection()
        timer = None
        if timeout_seconds and hasattr(cursor, 'interrupt'):
            timer = threading.Timer(timeout_seconds, cursor.interrupt)
            timer.daemon = True
            timer.start()
        try:
            cursor.execute(f"EXPLAIN {sql_clean}")
            return True
        finally:
            if timer:
                timer.cancel()
    except Exception as e:
        logger.warning(f"SQL syntax validation failed: {str(e)}")
        return False

def extract_filter_literals(sql_query, user_query=""):
    """
    Extract string literals from SQL WHERE clauses and natural language user query,
    ignoring common keywords, table formats, roles, and numeric/date constants.
    """
    literals = set()
    stopwords = {
        'movie', 'tvmovie', 'tvseries', 'short', 'tvepisode', 'video', 'tvshort', 'tvminiseries', 'tvspecial',
        'actor', 'actress', 'director', 'writer', 'producer', 'self', 'archive_footage', 'cinematographer', 'composer', 'editor',
        'drama', 'comedy', 'action', 'thriller', 'romance', 'adventure', 'sci-fi', 'horror', 'crime', 'mystery',
        'animation', 'fantasy', 'documentary', 'biography', 'history', 'family', 'music', 'musical', 'war', 'western', 'sport'
    }
    
    # Extract string literals in SQL (e.g., = 'foo' or LIKE '%foo%' or ILIKE '%foo%')
    sql_matches = re.findall(r"(?:=\s*'([^']+)'|LIKE\s*'([^']+)'|ILIKE\s*'([^']+)')", sql_query, flags=re.IGNORECASE)
    for group in sql_matches:
        for match in group:
            if match:
                cleaned = match.replace('%', '').strip()
                # Skip numeric constants, dates, short codes, and stopwords
                if (len(cleaned) >= 2 and 
                    not re.match(r'^\d+(\.\d+)?$', cleaned) and 
                    cleaned.lower() not in stopwords and 
                    cleaned.lower() not in ('us', 'gb', 'fr', 'de', 'jp', 'in', 'ca', 'au', 'en', 'es', 'it')):
                    literals.add(cleaned)

    if user_query:
        # Check for quoted phrases in user query
        quoted = re.findall(r'["\']([^"\']+)["\']', user_query)
        for q in quoted:
            cleaned_q = q.strip()
            if len(cleaned_q) >= 2 and not re.match(r'^\d+$', cleaned_q) and cleaned_q.lower() not in stopwords:
                literals.add(cleaned_q)

    return list(literals)

def probe_duckdb_entities(literals):
    """
    Check if extracted entity literals exist in DuckDB people or titles views.
    If exact match fails, use jaro_similarity to find high-confidence fuzzy matches.
    """
    probe_results = {}
    if not literals:
        return probe_results

    try:
        cursor = get_database_connection()
    except Exception as e:
        logger.warning(f"Could not get DB connection for entity probe: {e}")
        return probe_results

    for lit in literals:
        safe_lit = lit.replace("'", "''")
        item_probe = {
            "entity": lit,
            "person_exact": False,
            "title_exact": False,
            "person_fuzzy": [],
            "title_fuzzy": []
        }

        # 1. Probe people table (Exact)
        try:
            cursor.execute(f"SELECT name FROM people WHERE lower(name) = lower('{safe_lit}') LIMIT 1")
            exact_p = cursor.fetchone()
            if exact_p:
                item_probe["person_exact"] = True
                item_probe["exact_person_name"] = exact_p[0]
            else:
                # Probe people table (Fuzzy with jaro_similarity)
                cursor.execute(f"""
                    SELECT name, jaro_similarity(lower(name), lower('{safe_lit}')) AS score
                    FROM people
                    WHERE jaro_similarity(lower(name), lower('{safe_lit}')) > 0.80
                    ORDER BY score DESC
                    LIMIT 3
                """)
                rows = cursor.fetchall()
                if rows:
                    item_probe["person_fuzzy"] = [{"name": r[0], "similarity": round(float(r[1]), 3)} for r in rows]
        except Exception as e:
            logger.warning(f"Error probing people table for '{lit}': {e}")

        # 2. Probe titles table (Exact)
        try:
            cursor.execute(f"SELECT primary_title FROM titles WHERE lower(primary_title) = lower('{safe_lit}') LIMIT 1")
            exact_t = cursor.fetchone()
            if exact_t:
                item_probe["title_exact"] = True
                item_probe["exact_title_name"] = exact_t[0]
            else:
                # Probe titles table (Fuzzy with jaro_similarity)
                cursor.execute(f"""
                    SELECT primary_title, jaro_similarity(lower(primary_title), lower('{safe_lit}')) AS score
                    FROM titles
                    WHERE jaro_similarity(lower(primary_title), lower('{safe_lit}')) > 0.82
                    ORDER BY score DESC
                    LIMIT 3
                """)
                rows = cursor.fetchall()
                if rows:
                    item_probe["title_fuzzy"] = [{"title": r[0], "similarity": round(float(r[1]), 3)} for r in rows]
        except Exception as e:
            logger.warning(f"Error probing titles table for '{lit}': {e}")

        probe_results[lit] = item_probe

    return probe_results

# ══════════════════════════════════════════════════════════════════════
# Disambiguation & Entity Aliasing Knowledge Layer
# ══════════════════════════════════════════════════════════════════════

DISAMBIGUATION_REGISTRY = {
    "vijay": {
        "term": "Vijay",
        "primary_entity": "Joseph Vijay",
        "primary_label": "Joseph Vijay (Thalapathy)",
        "exclusion_tokens": ["sethupathi", "deverakonda", "antony", "raaz", "patkar", "chavan", "chiranjeevi", "joseph"],
        "alternatives": [
            {"name": "Vijay Sethupathi", "credits": 110, "query": "Vijay Sethupathi movies", "role": "Actor / Producer"},
            {"name": "Vijay Deverakonda", "credits": 31, "query": "Vijay Deverakonda movies", "role": "Actor"},
            {"name": "Vijay Antony", "credits": 108, "query": "Vijay Antony movies", "role": "Actor / Music Director"},
            {"name": "Vijay Raaz", "credits": 123, "query": "Vijay Raaz movies", "role": "Actor"}
        ]
    },
    "steve mcqueen": {
        "term": "Steve McQueen",
        "primary_entity": "Steve McQueen",
        "primary_label": "Steve McQueen",
        "exclusion_tokens": ["director", "slave", "hunger", "shame", "escape", "bullitt", "papillon", "magnificent seven"],
        "alternatives": [
            {"name": "Steve McQueen (Director)", "query": "12 Years a Slave directed by Steve McQueen", "role": "Director (12 Years a Slave, Shame)"},
            {"name": "Steve McQueen (Actor)", "query": "Movies starring Steve McQueen 1960s", "role": "Actor (The Great Escape, Bullitt)"}
        ]
    },
    "khan": {
        "term": "Khan",
        "primary_entity": "Shah Rukh Khan",
        "primary_label": "Shah Rukh Khan (SRK)",
        "exclusion_tokens": ["shah rukh", "srk", "salman", "aamir", "saif", "irrfan", "fardeen", "zayed", "genghis"],
        "alternatives": [
            {"name": "Salman Khan", "credits": 140, "query": "Salman Khan movies", "role": "Actor / Producer"},
            {"name": "Aamir Khan", "credits": 65, "query": "Aamir Khan movies", "role": "Actor / Director"},
            {"name": "Saif Ali Khan", "credits": 75, "query": "Saif Ali Khan movies", "role": "Actor"},
            {"name": "Irrfan Khan", "credits": 150, "query": "Irrfan Khan movies", "role": "Actor"}
        ]
    },
    "kapoor": {
        "term": "Kapoor",
        "primary_entity": "Ranbir Kapoor",
        "primary_label": "Ranbir Kapoor",
        "exclusion_tokens": ["ranbir", "raj", "kareena", "anil", "rishi", "shraddha", "karisma", "boney", "sanjay"],
        "alternatives": [
            {"name": "Raj Kapoor", "credits": 80, "query": "Raj Kapoor movies", "role": "Actor / Director"},
            {"name": "Kareena Kapoor", "credits": 75, "query": "Kareena Kapoor movies", "role": "Actress"},
            {"name": "Anil Kapoor", "credits": 145, "query": "Anil Kapoor movies", "role": "Actor / Producer"},
            {"name": "Rishi Kapoor", "credits": 160, "query": "Rishi Kapoor movies", "role": "Actor"}
        ]
    },
    "dune": {
        "term": "Dune",
        "primary_entity": "Dune (2021)",
        "primary_label": "Dune (2021 Denis Villeneuve)",
        "exclusion_tokens": ["1984", "lynch", "two", "part 2", "part two", "miniseries"],
        "alternatives": [
            {"name": "Dune (1984)", "query": "Dune 1984 David Lynch", "role": "David Lynch classic"},
            {"name": "Dune: Part Two (2024)", "query": "Dune Part Two 2024", "role": "Denis Villeneuve sequel"}
        ]
    },
    "avatar": {
        "term": "Avatar",
        "primary_entity": "Avatar (2009)",
        "primary_label": "Avatar (2009 James Cameron)",
        "exclusion_tokens": ["2022", "water", "airbender", "last airbender", "korra"],
        "alternatives": [
            {"name": "Avatar: The Way of Water (2022)", "query": "Avatar The Way of Water 2022", "role": "James Cameron sequel"},
            {"name": "The Last Airbender", "query": "The Last Airbender", "role": "Franchise adaptation"}
        ]
    },
    "batman": {
        "term": "Batman",
        "primary_entity": "Batman (1989)",
        "primary_label": "Batman (1989)",
        "exclusion_tokens": ["nolan", "bale", "dark knight", "pattinson", "keaton", "begins", "rises", "1989", "2022"],
        "alternatives": [
            {"name": "The Dark Knight Trilogy", "query": "Christopher Nolan Batman movies", "role": "Christian Bale / Nolan"},
            {"name": "The Batman (2022)", "query": "The Batman 2022 Robert Pattinson", "role": "Robert Pattinson / Matt Reeves"},
            {"name": "Batman (1989)", "query": "Batman 1989 Tim Burton", "role": "Michael Keaton / Tim Burton"}
        ]
    }
}

CANONICAL_ALIASES = {
    "srk": "Shah Rukh Khan",
    "king khan": "Shah Rukh Khan",
    "big b": "Amitabh Bachchan",
    "thala": "Ajith Kumar",
    "thalapathy": "Joseph Vijay",
    "thalapathy vijay": "Joseph Vijay",
    "superstar rajini": "Rajinikanth",
    "thalaivar": "Rajinikanth",
    "megastar chiranjeevi": "Chiranjeevi",
    "chiru": "Chiranjeevi",
    "power star": "Pawan Kalyan",
    "powerstar": "Pawan Kalyan",
    "rebel star": "Prabhas",
}

def detect_disambiguation(user_query, sql_query=""):
    """
    Detect if the user query refers to an ambiguous cinema entity
    (e.g., 'Vijay', 'Steve McQueen', 'Khan', 'Kapoor', 'Dune')
    and returns disambiguation metadata with alternative candidates.
    Does not trigger if the user has already specified a distinct disambiguating sub-entity or qualifier.
    """
    if not user_query:
        return None

    norm_q = user_query.lower().strip()
    words = set(re.findall(r'[a-zA-Z0-9]+', norm_q))

    # 1. Check Static Registry for known collision words
    for key, item in DISAMBIGUATION_REGISTRY.items():
        key_words = key.split()
        if all(kw in words for kw in key_words):
            # Check exclusions (e.g. if user already asked for 'Vijay Sethupathi', don't trigger 'Vijay')
            if any(exc in norm_q for exc in item.get("exclusion_tokens", [])):
                continue
            return {
                "term": item["term"],
                "primary_entity": item["primary_entity"],
                "primary_label": item["primary_label"],
                "alternatives": item["alternatives"]
            }

    # 2. Check Aliases (e.g. 'SRK movies' -> 'Shah Rukh Khan')
    for alias_key, target_name in CANONICAL_ALIASES.items():
        alias_words = alias_key.split()
        if all(aw in words for aw in alias_words):
            return {
                "term": alias_key.upper(),
                "primary_entity": target_name,
                "primary_label": f"{target_name} ({alias_key.upper()})",
                "alternatives": []
            }

    # 3. Dynamic candidate probe for single surname / mononym queries
    stop_tokens = {
        'movie', 'movies', 'film', 'films', 'actor', 'actress', 'directed', 'by', 
        'starring', 'in', 'the', 'best', 'top', 'all', 'of', 'show', 'shows', 'series'
    }
    candidate_tokens = [w for w in re.findall(r'[a-zA-Z]+', norm_q) if w not in stop_tokens and len(w) >= 4]
    if len(candidate_tokens) == 1:
        token = candidate_tokens[0]
        try:
            cursor = get_database_connection()
            safe_tok = token.replace("'", "''")
            query = f"""
                SELECT p.name, count(c.title_id) as credits, p.born
                FROM people p
                JOIN crew_lookup c ON c.person_id = p.person_id
                WHERE lower(p.name) = '{safe_tok}'
                   OR lower(p.name) LIKE '{safe_tok} %'
                   OR lower(p.name) LIKE '% {safe_tok}'
                GROUP BY p.name, p.born
                HAVING credits >= 25
                ORDER BY credits DESC
                LIMIT 5
            """
            rows = cursor.execute(query).fetchall()
            if len(rows) >= 2:
                primary = rows[0]
                alternatives = []
                for r in rows[1:]:
                    role_desc = f"Born {r[2]}" if r[2] else "Cinema Artist"
                    alternatives.append({
                        "name": r[0],
                        "credits": int(r[1]),
                        "query": f"{r[0]} movies",
                        "role": role_desc
                    })
                return {
                    "term": token.capitalize(),
                    "primary_entity": primary[0],
                    "primary_label": primary[0],
                    "alternatives": alternatives
                }
        except Exception as e:
            logger.warning(f"Error in dynamic candidate probe for '{token}': {e}")

    return None

def _responses_api_completion(client, model_name, messages):
    """Call Responses API while preserving system instructions and message roles."""
    system_messages = [message["content"] for message in messages if message["role"] == "system"]
    input_messages = [
        {"role": message["role"], "content": message["content"]}
        for message in messages
        if message["role"] != "system"
    ]
    kwargs = {
        "model": model_name,
        "input": input_messages
    }
    if system_messages:
        kwargs["instructions"] = "\n\n".join(system_messages)

    if hasattr(client, "responses") and hasattr(client.responses, "create"):
        response = client.responses.create(**kwargs)
    elif hasattr(client, "post"):
        try:
            raw = client.post("/responses", cast_to=object, body=kwargs)
        except Exception:
            raw = client.post("responses", cast_to=object, body=kwargs)
        if isinstance(raw, dict):
            output_text = raw.get("output_text")
            if not output_text and raw.get("output"):
                output_text = "\n".join([
                    c.get("text", "")
                    for item in raw.get("output", [])
                    for c in item.get("content", [])
                    if c.get("text")
                ])
            if output_text:
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=output_text))]
                )
        response = raw
    else:
        raise ValueError("Client does not support Responses API")

    output_text = getattr(response, "output_text", None)
    if not output_text:
        text_parts = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                text = getattr(content, "text", None)
                if text:
                    text_parts.append(text)
        output_text = "\n".join(text_parts)

    if not output_text:
        raise ValueError("Foundry Responses API returned no text output.")

    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=output_text))]
    )

def _should_use_responses_fallback(error):
    """Only retry API-shape failures, not auth, quota, or transient service errors."""
    status_code = getattr(error, "status_code", None)
    error_text = str(error).lower()
    if status_code in (404, 405):
        return True
    return ("chat completion" in error_text or "/openai/v1" in error_text) and any(
        phrase in error_text
        for phrase in ("not supported", "not allowed", "unsupported", "responses api", "policy")
    )

def safe_chat_completion(client, model_name, messages, temperature=None, response_format=None, max_tokens=1000):
    """
    Executes chat completion with fallback for models that enforce temperature=1 / no custom temperature
    (e.g., gpt-5.6-luna, reasoning models, OpenAI o-series) or use the responses API / deployment routing.
    """
    kwargs = {
        "model": model_name,
        "messages": messages
    }
    
    is_reasoning_or_luna = any(kw in model_name.lower() for kw in ["luna", "o1", "o3", "gpt-5"])
    
    if temperature is not None and not is_reasoning_or_luna:
        kwargs["temperature"] = temperature
        
    if response_format is not None:
        kwargs["response_format"] = response_format

    if max_tokens is not None and not is_reasoning_or_luna:
        kwargs["max_tokens"] = max_tokens
        
    while True:
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as error:
            error_text = str(error).lower()
            if "temperature" in error_text and "temperature" in kwargs:
                logger.info(f"Retrying chat completion without temperature for model {model_name}")
                kwargs.pop("temperature")
                continue
            if "max_tokens" in error_text and "max_tokens" in kwargs:
                logger.info(f"Retrying chat completion without max_tokens for model {model_name}")
                kwargs.pop("max_tokens")
                continue
            if "response_format" in error_text and "response_format" in kwargs:
                logger.info(f"Retrying chat completion without response_format for model {model_name}")
                kwargs.pop("response_format")
                continue

            if _should_use_responses_fallback(error):
                # 1. Try AzureOpenAI deployment routing if credentials are available
                creds = getattr(client, "_azure_creds", None)
                if creds and isinstance(creds, dict) and not isinstance(client, AzureOpenAI):
                    try:
                        clean_ep = re.sub(r'/openai.*$', '', str(creds.get("endpoint") or ""))
                        if clean_ep and clean_ep.startswith("http"):
                            logger.info(f"Retrying with AzureOpenAI deployment-routed client at {clean_ep}...")
                            az_client = AzureOpenAI(
                                azure_endpoint=clean_ep,
                                api_version=str(creds.get("api_version") or "2025-04-01-preview"),
                                api_key=str(creds.get("api_key") or "")
                            )
                            return az_client.chat.completions.create(**kwargs)
                    except Exception as az_err:
                        logger.warning(f"AzureOpenAI deployment route fallback failed: {az_err}")

                # 2. Try Responses API
                if hasattr(client, "responses") or hasattr(client, "post"):
                    try:
                        logger.info(f"Chat Completions unavailable for {model_name}; using Responses API")
                        return _responses_api_completion(client, model_name, messages)
                    except Exception as resp_err:
                        logger.warning(f"Responses API fallback failed: {resp_err}")

            status_code = getattr(error, "status_code", None)
            err_response = getattr(error, "response", None)
            resp_text = getattr(err_response, "text", str(error)) if err_response else str(error)
            req_url = getattr(err_response, "request", None)
            req_url_str = str(req_url.url) if req_url and hasattr(req_url, "url") else "N/A"
            logger.error("=" * 60)
            logger.error(f"[AZURE CALL FAILED]")
            logger.error(f"  Target URL : {req_url_str}")
            logger.error(f"  Status Code: {status_code}")
            logger.error(f"  Response   : {resp_text}")
            logger.error("=" * 60)
            raise

def reflect_on_zero_results(user_query, initial_sql, probe_data, creds=None):
    """
    Intelligent reflection step: Uses AI grounded with database probe results
    to classify why 0 rows were returned and generate a corrected SQL query if appropriate.
    """
    client, model_name = get_azure_client(creds=creds)

    probe_summary_lines = []
    for lit, pdata in probe_data.items():
        if pdata.get("person_exact"):
            probe_summary_lines.append(f"- Entity '{lit}': Verified exact match for Person '{pdata.get('exact_person_name')}'.")
        elif pdata.get("person_fuzzy"):
            top_sug = pdata["person_fuzzy"][0]
            probe_summary_lines.append(f"- Entity '{lit}': NOT found in people. Top fuzzy match in database is '{top_sug['name']}' (similarity score: {top_sug['similarity']}).")
        
        if pdata.get("title_exact"):
            probe_summary_lines.append(f"- Entity '{lit}': Verified exact match for Title '{pdata.get('exact_title_name')}'.")
        elif pdata.get("title_fuzzy"):
            top_sug = pdata["title_fuzzy"][0]
            probe_summary_lines.append(f"- Entity '{lit}': NOT found in titles. Top fuzzy match in database is '{top_sug['title']}' (similarity score: {top_sug['similarity']}).")

        if not pdata.get("person_exact") and not pdata.get("person_fuzzy") and not pdata.get("title_exact") and not pdata.get("title_fuzzy"):
            probe_summary_lines.append(f"- Entity '{lit}': Not found in people or titles (no close match).")

    probe_context = "\n".join(probe_summary_lines) if probe_summary_lines else "No specific entities extracted."

    system_prompt = f"""
You are an expert IMDb text-to-SQL diagnostic agent.
A user executed a natural language search query, but the generated SQL query returned 0 results from the IMDb database.

DATABASE SCHEMA:
{DB_SCHEMA_PROMPT}

PHYSICAL DESIGN:
- Start person searches with: WITH matched_people AS MATERIALIZED (SELECT person_id, name FROM people WHERE name = '...')
- Use crew_lookup for person-to-title joins.
- Use titles type IN ('movie', 'tvMovie') for movies.

DATABASE PROBE EVIDENCE:
{probe_context}

YOUR TASK:
Analyze whether the 0 results were caused by:
1. "MISSPELLED_ENTITY": A typo or misspelling in person names or titles (e.g. 'gorge clooney' -> 'George Clooney'). Use the verified fuzzy matches from the database evidence!
2. "OVERLY_STRICT_FILTER": The entity exists and is verified, but overly strict WHERE constraints (e.g. impossible release year, rating threshold > 9.9, or specific genre) produced 0 rows.
3. "GENUINE_EMPTY": The entity was found and verified, but no matching cinema records legitimately exist for that combination (e.g. Tom Hanks has no 1975 sci-fi movies). DO NOT invent fictional data or substitute unrelated actors.

RESPOND STRICTLY IN VALID JSON with the following schema:
{{
  "diagnosis": "MISSPELLED_ENTITY" | "OVERLY_STRICT_FILTER" | "GENUINE_EMPTY",
  "explanation": "Clear, concise user-facing message explaining the finding",
  "corrected_entity": "The corrected entity string (e.g. 'George Clooney') or null",
  "corrected_sql": "Valid DuckDB SQL query string incorporating the correction, or null if GENUINE_EMPTY"
}}
"""

    user_message = f"""
User Query: "{user_query}"
Initial SQL: {initial_sql}
Result: 0 rows returned.

Diagnose and provide the JSON response.
"""

    try:
        response = safe_chat_completion(
            client=client,
            model_name=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content.strip()
        
        # Robust JSON extraction
        clean_json = re.sub(r'^```(?:json)?\s*', '', content, flags=re.IGNORECASE)
        clean_json = re.sub(r'\s*```$', '', clean_json)
        json_match = re.search(r'(\{[\s\S]*\})', clean_json)
        if json_match:
            data = json.loads(json_match.group(1))
        else:
            data = json.loads(clean_json)
        
        if data.get("corrected_sql"):
            sql = data["corrected_sql"]
            sql = re.sub(r'^```sql\s*', '', sql, flags=re.IGNORECASE)
            sql = re.sub(r'^```\s*', '', sql)
            sql = re.sub(r'\s*```$', '', sql)
            data["corrected_sql"] = optimize_generated_sql(
                fix_single_quotes_in_sql(sql.strip())
            )
            
        return data
    except Exception as e:
        logger.error(f"Error in zero-result reflection: {e}")
        return {
            "diagnosis": "GENUINE_EMPTY",
            "explanation": "No matching records found.",
            "corrected_entity": None,
            "corrected_sql": None
        }

def generate_response(user_query, creds=None):
    """
    Generate SQL query response using Azure OpenAI with prompt engineering
    """
    start_time = time.time()
    logger.info(f"Processing query: '{user_query}'")
    
    client, model_name = get_azure_client(creds=creds)
    
    system_message = f"""
You generate read-only DuckDB SQL for IMDb search.

{DB_SCHEMA_PROMPT}

PHYSICAL DESIGN:
- people.name, people.person_id, titles.title_id, and ratings.title_id have lookup indexes.
- crew_lookup is a compact copy of person_id/category/title_id sorted by person_id.
- crew is a much larger detail table. Use it only when job or characters is requested.

RULES:
1. Return one SELECT or WITH query and no prose or markdown.
2. Use exact people.name equality. Never add OR LIKE to a name; zero-result recovery handles misspellings.
3. Start person searches with a MATERIALIZED matched_people CTE so the name index resolves IDs before credit joins.
4. Use crew_lookup for every person-to-title relationship:
   - For directing credits: c.category = 'director'
   - For acting credits: c.category IN ('actor', 'actress')
   - For writing credits: c.category = 'writer'
5. For multiple named people (co-stars or actor+director):
   - Group credits by title_id and require COUNT(DISTINCT p.name) to equal the number of people.
   - For actor + director combos: require (p.name = 'Director Name' AND c.category = 'director') OR (p.name = 'Actor Name' AND c.category IN ('actor', 'actress')).
6. For title discovery searches: Include title_id, primary_title, premiered, genres, rating, votes, and poster_path when they fit the request.
7. Prevent genuine duplicate titles with DISTINCT or GROUP BY.
8. Filter title types:
   - For movies: WHERE t.type IN ('movie', 'tvMovie')
   - For TV shows / series: WHERE t.type IN ('tvSeries', 'tvMiniSeries')
   - For TV miniseries: WHERE t.type = 'tvMiniSeries'
9. Filter country of origin & language (universal):
   - Regional languages: Telugu ('te'), Hindi ('hi'), Tamil ('ta'), Malayalam ('ml'), Kannada ('kn'), Korean ('ko'), Japanese ('ja'), French ('fr'), Spanish ('es'), German ('de'), Italian ('it'), Portuguese ('pt'), Russian ('ru'), Chinese ('zh').
   - Countries: India ('IN'), France ('FR'), Japan ('JP'), South Korea ('KR'), Mexico ('MX'), Canada ('CA'), Germany ('DE'), Italy ('IT'), Spain ('ES'), United Kingdom ('GB'), United States ('US').
   - When searching by language (e.g. 'Telugu movies', 'Spanish thrillers', 'Korean cinema', 'Japanese anime'): use t.original_language = '<LANG_CODE>'.
   - When searching by country (e.g. 'movies from France', 'movies from India', 'Canadian movies'): use t.origin_country = '<COUNTRY_CODE>'.
10. Add a deterministic ORDER BY and LIMIT 100 for title discovery searches. For aggregate, trend, or ranking queries, omit LIMIT unless top-N is explicitly asked (e.g. LIMIT 10).
11. Escape apostrophes inside string literals by doubling them (e.g. 'Schindler''s List').
12. Analytical, Quantitative, and Aggregation Queries:
    - When the user asks "how many", "count", "per year", "for each year", "average rating", "trend", "distribution", "breakdown", or "ranking":
    - Group by the appropriate column (e.g. GROUP BY t.premiered for yearly trends, or GROUP BY t.genres).
    - For yearly/temporal trends, ALWAYS add `WHERE t.premiered IS NOT NULL` (or `AND t.premiered IS NOT NULL`) so unreleased or undated titles do not create a null year bucket.
    - Always use meaningful, standard column aliases: 'year', 'movie_count', 'avg_rating', 'total_movies', 'total_titles'.
    - Always count distinct titles using COUNT(DISTINCT t.title_id) AS movie_count so multiple roles or joins do not inflate film counts.
    - Chronological ordering: For yearly trends, use ORDER BY year ASC (or premiered ASC).
    - For single-number scalar questions (e.g. "how many movies has Christopher Nolan directed?"), return 1 row: SELECT COUNT(DISTINCT t.title_id) AS total_movies ...
    - Do NOT select poster_path, title_id, or primary_title in the top-level SELECT when producing an aggregate summary.
13. Entity Disambiguation, Popular Aliases, and Homonyms:
    - In IMDb, "Thalapathy Vijay" or generic "Vijay" (Tamil cinema superstar) is officially registered as 'Joseph Vijay' (person_id nm0897201). NEVER use WHERE name = 'Vijay' for Thalapathy Vijay. Only use 'Vijay Sethupathi' if Sethupathi is specified, or 'Vijay Deverakonda' if Deverakonda is specified.
    - For "Steve McQueen": For directing or modern films (e.g. "12 Years a Slave", "Hunger", "Shame"), use director credits (nm2588606, born 1969). For classic 1960s-1970s acting ("Bullitt", "The Great Escape"), use actor credits (nm0000537).
    - Map popular aliases and mononyms to their canonical IMDb people.name:
      * "SRK" or "King Khan" -> 'Shah Rukh Khan'
      * "Big B" -> 'Amitabh Bachchan'
      * "Thala" -> 'Ajith Kumar'
      * "Superstar" or "Thalaivar" -> 'Rajinikanth'
      * "Megastar" or "Chiru" -> 'Chiranjeevi'
      * "Power Star" -> 'Pawan Kalyan'
      * "Rebel Star" -> 'Prabhas'

EXAMPLES:

User: Christopher Nolan movies
SQL:
WITH matched_people AS MATERIALIZED (
    SELECT person_id
    FROM people
    WHERE name = 'Christopher Nolan'
)
SELECT DISTINCT t.title_id, t.primary_title, t.premiered, t.genres, r.rating, r.votes, t.poster_path
FROM matched_people p
JOIN crew_lookup c ON c.person_id = p.person_id AND c.category = 'director'
JOIN titles t ON t.title_id = c.title_id AND t.type IN ('movie', 'tvMovie')
LEFT JOIN ratings r ON r.title_id = t.title_id
ORDER BY r.rating DESC NULLS LAST, r.votes DESC NULLS LAST, t.premiered DESC
LIMIT 100;

User: Vijay movies
SQL:
WITH matched_people AS MATERIALIZED (
    SELECT person_id
    FROM people
    WHERE name = 'Joseph Vijay'
)
SELECT DISTINCT t.title_id, t.primary_title, t.premiered, t.genres, r.rating, r.votes, t.poster_path
FROM matched_people p
JOIN crew_lookup c ON c.person_id = p.person_id AND c.category IN ('actor', 'actress')
JOIN titles t ON t.title_id = c.title_id AND t.type IN ('movie', 'tvMovie')
LEFT JOIN ratings r ON r.title_id = t.title_id
ORDER BY r.rating DESC NULLS LAST, r.votes DESC NULLS LAST, t.premiered DESC
LIMIT 100;

User: Vijay Sethupathi movies
SQL:
WITH matched_people AS MATERIALIZED (
    SELECT person_id
    FROM people
    WHERE name = 'Vijay Sethupathi'
)
SELECT DISTINCT t.title_id, t.primary_title, t.premiered, t.genres, r.rating, r.votes, t.poster_path
FROM matched_people p
JOIN crew_lookup c ON c.person_id = p.person_id AND c.category IN ('actor', 'actress')
JOIN titles t ON t.title_id = c.title_id AND t.type IN ('movie', 'tvMovie')
LEFT JOIN ratings r ON r.title_id = t.title_id
ORDER BY r.rating DESC NULLS LAST, r.votes DESC NULLS LAST, t.premiered DESC
LIMIT 100;

User: SRK movies
SQL:
WITH matched_people AS MATERIALIZED (
    SELECT person_id
    FROM people
    WHERE name = 'Shah Rukh Khan'
)
SELECT DISTINCT t.title_id, t.primary_title, t.premiered, t.genres, r.rating, r.votes, t.poster_path
FROM matched_people p
JOIN crew_lookup c ON c.person_id = p.person_id AND c.category IN ('actor', 'actress')
JOIN titles t ON t.title_id = c.title_id AND t.type IN ('movie', 'tvMovie')
LEFT JOIN ratings r ON r.title_id = t.title_id
ORDER BY r.rating DESC NULLS LAST, r.votes DESC NULLS LAST, t.premiered DESC
LIMIT 100;

User: how many movies did Brahmanandam act in for each year between 2020 and 2025
SQL:
WITH matched_people AS MATERIALIZED (
    SELECT person_id
    FROM people
    WHERE name = 'Brahmanandam'
)
SELECT t.premiered AS year, COUNT(DISTINCT t.title_id) AS movie_count
FROM matched_people p
JOIN crew_lookup c ON c.person_id = p.person_id AND c.category IN ('actor', 'actress')
JOIN titles t ON t.title_id = c.title_id AND t.type IN ('movie', 'tvMovie')
WHERE t.premiered BETWEEN 2020 AND 2025
GROUP BY t.premiered
ORDER BY year ASC;

User: how many movies has Christopher Nolan directed?
SQL:
WITH matched_people AS MATERIALIZED (
    SELECT person_id
    FROM people
    WHERE name = 'Christopher Nolan'
)
SELECT COUNT(DISTINCT t.title_id) AS total_movies
FROM matched_people p
JOIN crew_lookup c ON c.person_id = p.person_id AND c.category = 'director'
JOIN titles t ON t.title_id = c.title_id AND t.type IN ('movie', 'tvMovie');

User: Movies where Quentin Tarantino acted
SQL:
WITH matched_people AS MATERIALIZED (
    SELECT person_id
    FROM people
    WHERE name = 'Quentin Tarantino'
)
SELECT DISTINCT t.title_id, t.primary_title, t.premiered, t.genres, r.rating, r.votes, t.poster_path
FROM matched_people p
JOIN crew_lookup c ON c.person_id = p.person_id AND c.category IN ('actor', 'actress')
JOIN titles t ON t.title_id = c.title_id AND t.type IN ('movie', 'tvMovie')
LEFT JOIN ratings r ON r.title_id = t.title_id
ORDER BY r.rating DESC NULLS LAST, r.votes DESC NULLS LAST, t.premiered DESC
LIMIT 100;

User: Martin Scorsese movies starring Robert De Niro
SQL:
WITH matched_people AS MATERIALIZED (
    SELECT person_id, name
    FROM people
    WHERE name IN ('Martin Scorsese', 'Robert De Niro')
),
shared_titles AS (
    SELECT c.title_id
    FROM matched_people p
    JOIN crew_lookup c ON c.person_id = p.person_id
    WHERE (p.name = 'Martin Scorsese' AND c.category = 'director')
       OR (p.name = 'Robert De Niro' AND c.category IN ('actor', 'actress'))
    GROUP BY c.title_id
    HAVING COUNT(DISTINCT p.name) = 2
)
SELECT t.title_id, t.primary_title, t.premiered, t.genres, r.rating, r.votes, t.poster_path
FROM shared_titles s
JOIN titles t ON t.title_id = s.title_id AND t.type IN ('movie', 'tvMovie')
LEFT JOIN ratings r ON r.title_id = t.title_id
ORDER BY r.rating DESC NULLS LAST, r.votes DESC NULLS LAST, t.premiered DESC
LIMIT 100;

User: Top rated Telugu action movies
SQL:
SELECT t.title_id, t.primary_title, t.premiered, t.genres, r.rating, r.votes, t.poster_path
FROM titles t
JOIN ratings r ON r.title_id = t.title_id
WHERE t.type IN ('movie', 'tvMovie')
  AND t.original_language = 'te'
  AND t.genres LIKE '%Action%'
  AND r.votes >= 5000
ORDER BY r.rating DESC, r.votes DESC, t.premiered DESC
LIMIT 100;

User: Telugu movies released each year since 2020
SQL:
SELECT t.premiered AS year, COUNT(DISTINCT t.title_id) AS movie_count
FROM titles t
WHERE t.type IN ('movie', 'tvMovie')
  AND t.original_language = 'te'
  AND t.premiered >= 2020
GROUP BY t.premiered
ORDER BY year ASC;

User: Avatar 2009
SQL:
SELECT t.title_id, t.primary_title, t.premiered, t.genres, r.rating, r.votes, t.poster_path
FROM titles t
LEFT JOIN ratings r ON r.title_id = t.title_id
WHERE t.primary_title = 'Avatar'
  AND t.premiered = 2009
  AND t.type IN ('movie', 'tvMovie')
LIMIT 10;
"""
    
    try:
        response = safe_chat_completion(
            client=client,
            model_name=model_name,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_query}
            ],
            temperature=0.2
        )
        
        sql_query = response.choices[0].message.content.strip()
        
        # Clean up markdown code blocks if present
        sql_query = re.sub(r'^```sql\s*', '', sql_query, flags=re.IGNORECASE)
        sql_query = re.sub(r'^```\s*', '', sql_query)
        sql_query = re.sub(r'\s*```$', '', sql_query)
        sql_query = sql_query.strip()
        
        sql_query = optimize_generated_sql(fix_single_quotes_in_sql(sql_query))
        
        processing_time = time.time() - start_time
        logger.info(f"Generated SQL in {processing_time:.2f}s: {sql_query[:100]}...")
        
        return sql_query
        
    except Exception as e:
        logger.error(f"Error generating SQL: {str(e)}")
        raise

def get_suggested_queries():
    """Return a list of suggested example queries"""
    return [
        "Tom Hanks movies",
        "Best 2010s sci-fi",
        "Christopher Nolan films",
        "DiCaprio & Winslet movies"
    ]

def get_title_info(title_id):
    """Get detailed information about a specific title"""
    try:
        cursor = get_database_connection()
        query = f"""
        SELECT t.title_id, t.primary_title, t.original_title, t.premiered, t.ended, 
               t.runtime_minutes, t.genres, t.type, r.rating, r.votes, t.poster_path
        FROM titles t
        LEFT JOIN ratings r ON t.title_id = r.title_id
        WHERE t.title_id = '{title_id.replace("'", "''")}'
        LIMIT 1
        """
        cursor.execute(query)
        results = cursor.fetchall()
        column_names = [desc[0] for desc in cursor.description] if cursor.description else []
        
        if results:
            return dict(zip(column_names, results[0]))
        return None
        
    except Exception as e:
        logger.error(f"Error fetching title info: {str(e)}")
        return None

def generate_title_summary(title_name, title_info, creds=None):
    """Generate AI summary for a movie/TV show"""
    try:
        client, model_name = get_azure_client(creds=creds)
        
        context = f"Title: {title_name}\n"
        if title_info:
            if title_info.get('premiered'):
                context += f"Released: {title_info['premiered']}\n"
            if title_info.get('genres'):
                context += f"Genres: {title_info['genres']}\n"
            if title_info.get('rating'):
                context += f"IMDb Rating: {title_info['rating']}/10 ({title_info.get('votes', 0)} votes)\n"
            if title_info.get('runtime_minutes'):
                context += f"Runtime: {title_info['runtime_minutes']} minutes\n"
        
        prompt = f"""
        Please provide a brief, informative summary about this {title_info.get('type', 'title') if title_info else 'title'}:
        
        {context}
        
        Include key information like plot, notable cast/crew, cultural impact, or interesting trivia. 
        Keep it concise but engaging (2-3 paragraphs maximum).
        """
        
        response = safe_chat_completion(
            client=client,
            model_name=model_name,
            messages=[
                {"role": "system", "content": "You are a knowledgeable film and TV expert who provides engaging summaries."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        logger.error(f"Error generating title summary: {str(e)}")
        return "Unable to generate summary at this time."

# ----------------- ROUTES ----------------- #

@main.route('/api/config-status', methods=['GET'])
def api_config_status():
    """Health status endpoint"""
    return jsonify({
        "status": "healthy"
    })

@main.route('/api/search/stream', methods=['POST'])
def api_search_stream():
    """
    Streaming Server-Sent Events (SSE) search endpoint.
    Provides live step-by-step progress telemetry, reflection on zero-results,
    and supports immediate cancellation via client AbortController.
    """
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()
    creds = get_azure_credentials(request)
    data = request.get_json(silent=True) or {}
    user_query = data.get('query', '').strip()

    def generate_events():
        if not user_query or len(user_query) < 3:
            yield f"data: {json.dumps({'type': 'error', 'error': 'Please enter a search query (at least 3 characters).', 'suggestions': get_suggested_queries()[:4]})}\n\n"
            return

        logger.info(f"[{request_id}] Streaming search: '{user_query}'")

        # Step 1: Understanding Query & Synthesis
        yield f"data: {json.dumps({'type': 'status', 'stage': 'synthesizing', 'title': 'Interpreting Query', 'message': 'Understanding your movie criteria, actors & release era...'})}\n\n"
        
        try:
            sql_query = generate_response(user_query, creds=creds)
        except Exception as e:
            logger.error(f"[{request_id}] Query interpretation failed: {e}")
            yield f"data: {json.dumps({'type': 'error', 'error': f'Could not interpret search: {str(e)}', 'suggestions': get_suggested_queries()[:4]})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'sql', 'stage': 'sql_ready', 'sql': sql_query, 'attempt': 1})}\n\n"

        # Step 2: Validate Schema & Constraints
        yield f"data: {json.dumps({'type': 'status', 'stage': 'validating', 'title': 'Checking Catalog', 'message': 'Matching against IMDb catalog & film records...'})}\n\n"
        if not validate_sql_query(sql_query):
            yield f"data: {json.dumps({'type': 'status', 'stage': 'refining', 'title': 'Refining Search', 'message': 'Refining search criteria for best accuracy...'})}\n\n"
            try:
                retry_query = f"Regenerate valid DuckDB SQL for: {user_query}"
                sql_query = generate_response(retry_query, creds=creds)
            except Exception as e:
                pass

            if not validate_sql_query(sql_query):
                yield f"data: {json.dumps({'type': 'error', 'error': 'Could not process this query. Try rephrasing with simpler keywords.', 'sql_query': sql_query, 'suggestions': get_suggested_queries()[:4]})}\n\n"
                return

        # Step 3: Searching catalog
        yield f"data: {json.dumps({'type': 'status', 'stage': 'executing', 'title': 'Searching Vault', 'message': 'Searching 10M+ titles, cast & ratings...'})}\n\n"

        try:
            results, column_names = execute_sql_query(sql_query)
        except Exception as e:
            logger.error(f"[{request_id}] Query execution error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'error': f'Search failed: {str(e)}', 'sql_query': sql_query})}\n\n"
            return

        total_rows = len(results)

        # If we got results on first attempt, stream them immediately!
        if total_rows > 0:
            execution_time = round(time.time() - start_time, 2)
            if total_rows > 1000:
                results = results[:1000]
            results_dicts = [dict(zip(column_names, row)) for row in results]
            
            query_type = classify_query_result(column_names, results, sql_query)
            is_aggregate = (query_type in ("AGGREGATION_SERIES", "AGGREGATION_SCALAR"))
            drilldown_results = []
            drilldown_cols = []
            drilldown_sql = None

            if is_aggregate:
                drilldown_sql = derive_detail_sql(sql_query)
                if drilldown_sql and validate_sql_query(drilldown_sql):
                    try:
                        dd_rows, dd_cols = execute_sql_query(drilldown_sql, max_rows=300)
                        drilldown_cols = dd_cols
                        drilldown_results = [dict(zip(dd_cols, row)) for row in dd_rows]
                    except Exception as e:
                        logger.warning(f"[{request_id}] Drilldown execution failed: {e}")

            logger.info(f"[{request_id}] Search success ({query_type}): {total_rows} rows in {execution_time}s")
            
            if is_aggregate:
                prep_msg = f"Calculated cinema trends across {total_rows} data points..."
            else:
                prep_msg = f"Found {total_rows:,} matching cinema titles..."
                
            yield f"data: {json.dumps({'type': 'status', 'stage': 'compiling', 'title': 'Preparing Results', 'message': prep_msg})}\n\n"
            disambig_data = detect_disambiguation(user_query, sql_query)
            result_payload = {
                'type': 'result',
                'success': True,
                'results': results_dicts,
                'column_names': column_names,
                'sql_query': sql_query,
                'row_count': total_rows,
                'execution_time': execution_time,
                'query': user_query,
                'stage': 'completed',
                'query_type': query_type,
                'is_aggregate': is_aggregate,
                'drilldown_results': drilldown_results,
                'drilldown_columns': drilldown_cols,
                'drilldown_sql': drilldown_sql,
                'disambiguation': disambig_data
            }
            yield f"data: {json.dumps(result_payload)}\n\n"
            return

        # Step 4: 0 rows returned -> Check for typos / intent matching
        yield f"data: {json.dumps({'type': 'status', 'stage': 'probing', 'title': 'Smart Matching', 'message': 'Checking title spelling & finding closest matches...'})}\n\n"

        literals = extract_filter_literals(sql_query, user_query)
        probe_data = probe_duckdb_entities(literals)

        yield f"data: {json.dumps({'type': 'status', 'stage': 'reflecting', 'title': 'Smart Matching', 'message': 'Searching for closest name & keyword matches...'})}\n\n"

        reflection = reflect_on_zero_results(user_query, sql_query, probe_data, creds=creds)
        diagnosis = reflection.get("diagnosis", "GENUINE_EMPTY")
        explanation = reflection.get("explanation", "No matching records found.")
        corrected_sql = reflection.get("corrected_sql")
        corrected_entity = reflection.get("corrected_entity")

        if diagnosis in ("MISSPELLED_ENTITY", "OVERLY_STRICT_FILTER") and corrected_sql and validate_sql_query(corrected_sql):
            retry_payload = {
                'type': 'retry',
                'stage': 'retrying',
                'title': 'Smart Match',
                'message': f"Searching for '{corrected_entity}' instead...",
                'corrected_entity': corrected_entity,
                'new_sql': corrected_sql,
                'attempt': 2
            }
            yield f"data: {json.dumps(retry_payload)}\n\n"
            try:
                retry_results, retry_cols = execute_sql_query(corrected_sql)
                retry_rows = len(retry_results)
                execution_time = round(time.time() - start_time, 2)
                
                if retry_rows > 0:
                    if retry_rows > 1000:
                        retry_results = retry_results[:1000]
                    retry_dicts = [dict(zip(retry_cols, row)) for row in retry_results]
                    
                    retry_query_type = classify_query_result(retry_cols, retry_results, corrected_sql)
                    retry_is_agg = (retry_query_type in ("AGGREGATION_SERIES", "AGGREGATION_SCALAR"))
                    retry_dd_results = []
                    retry_dd_cols = []
                    retry_dd_sql = None
                    if retry_is_agg:
                        retry_dd_sql = derive_detail_sql(corrected_sql)
                        if retry_dd_sql and validate_sql_query(retry_dd_sql):
                            try:
                                r_rows, r_cols = execute_sql_query(retry_dd_sql, max_rows=300)
                                retry_dd_cols = r_cols
                                retry_dd_results = [dict(zip(r_cols, row)) for row in r_rows]
                            except Exception as e:
                                logger.warning(f"[{request_id}] Re-query drilldown failed: {e}")

                    logger.info(f"[{request_id}] Auto-corrected search success: {retry_rows} rows in {execution_time}s")
                    retry_disambig_data = detect_disambiguation(user_query, corrected_sql)
                    retry_result_payload = {
                        'type': 'result',
                        'success': True,
                        'results': retry_dicts,
                        'column_names': retry_cols,
                        'sql_query': corrected_sql,
                        'original_sql': sql_query,
                        'row_count': retry_rows,
                        'execution_time': execution_time,
                        'correction_note': explanation,
                        'corrected_entity': corrected_entity,
                        'diagnosis': diagnosis,
                        'query': user_query,
                        'stage': 'completed',
                        'query_type': retry_query_type,
                        'is_aggregate': retry_is_agg,
                        'drilldown_results': retry_dd_results,
                        'drilldown_columns': retry_dd_cols,
                        'drilldown_sql': retry_dd_sql,
                        'disambiguation': retry_disambig_data
                    }
                    yield f"data: {json.dumps(retry_result_payload)}\n\n"
                    return
            except Exception as e:
                logger.warning(f"[{request_id}] Re-query failed: {e}")

        # If still 0 results or genuine empty
        execution_time = round(time.time() - start_time, 2)
        empty_disambig_data = detect_disambiguation(user_query, sql_query)
        empty_payload = {
            'type': 'result',
            'success': True,
            'results': [],
            'column_names': column_names,
            'sql_query': sql_query,
            'row_count': 0,
            'execution_time': execution_time,
            'explanation': explanation,
            'diagnosis': diagnosis,
            'query': user_query,
            'stage': 'completed',
            'is_aggregate': False,
            'disambiguation': empty_disambig_data
        }
        yield f"data: {json.dumps(empty_payload)}\n\n"

    return Response(stream_with_context(generate_events()), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no'
    })

@main.route('/api/search', methods=['POST'])
def api_search():
    """AJAX search endpoint (fallback / non-streaming)"""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()
    creds = get_azure_credentials(request)
    
    try:
        data = request.get_json() or {}
        user_query = data.get('query', '').strip()
        
        if not user_query or len(user_query) < 3:
            return jsonify({
                'success': False,
                'error': 'Please enter a search query (at least 3 characters).',
                'suggestions': get_suggested_queries()[:4]
            }), 400
        
        logger.info(f"[{request_id}] AJAX search: '{user_query}'")
        
        # Generate SQL
        sql_query = generate_response(user_query, creds=creds)
        
        # Validate SQL
        if not validate_sql_query(sql_query):
            logger.warning(f"[{request_id}] SQL validation failed, attempting re-prompt...")
            retry_query = f"Regenerate valid DuckDB SQL for: {user_query}"
            sql_query = generate_response(retry_query, creds=creds)
            
            if not validate_sql_query(sql_query):
                return jsonify({
                    'success': False,
                    'error': 'Could not generate a valid query. Try rephrasing with simpler keywords.',
                    'sql_query': sql_query,
                    'suggestions': get_suggested_queries()[:4]
                }), 400
        
        # Execute query
        results, column_names = execute_sql_query(sql_query)
        total_rows = len(results)
        correction_note = None
        corrected_entity = None
        diagnosis = None

        # Reflection if 0 rows returned
        if total_rows == 0:
            literals = extract_filter_literals(sql_query, user_query)
            probe_data = probe_duckdb_entities(literals)
            reflection = reflect_on_zero_results(user_query, sql_query, probe_data, creds=creds)
            diagnosis = reflection.get("diagnosis")
            correction_note = reflection.get("explanation")
            corrected_entity = reflection.get("corrected_entity")
            corrected_sql = reflection.get("corrected_sql")

            if diagnosis in ("MISSPELLED_ENTITY", "OVERLY_STRICT_FILTER") and corrected_sql and validate_sql_query(corrected_sql):
                try:
                    retry_results, retry_cols = execute_sql_query(corrected_sql)
                    if len(retry_results) > 0:
                        results = retry_results
                        column_names = retry_cols
                        sql_query = corrected_sql
                        total_rows = len(results)
                except Exception as e:
                    logger.warning(f"[{request_id}] Fallback retry failed: {e}")

        execution_time = round(time.time() - start_time, 2)
        if total_rows > 1000:
            results = results[:1000]
            
        results_dicts = [dict(zip(column_names, row)) for row in results]
        
        query_type = classify_query_result(column_names, results, sql_query)
        is_aggregate = (query_type in ("AGGREGATION_SERIES", "AGGREGATION_SCALAR"))
        drilldown_results = []
        drilldown_cols = []
        drilldown_sql = None

        if is_aggregate:
            drilldown_sql = derive_detail_sql(sql_query)
            if drilldown_sql and validate_sql_query(drilldown_sql):
                try:
                    dd_rows, dd_cols = execute_sql_query(drilldown_sql, max_rows=300)
                    drilldown_cols = dd_cols
                    drilldown_results = [dict(zip(dd_cols, row)) for row in dd_rows]
                except Exception as e:
                    logger.warning(f"[{request_id}] Fallback drilldown failed: {e}")

        logger.info(f"[{request_id}] Search returned {total_rows} rows ({query_type}) in {execution_time}s")
        
        disambig_data = detect_disambiguation(user_query, sql_query)
        return jsonify({
            'success': True,
            'results': results_dicts,
            'column_names': column_names,
            'sql_query': sql_query,
            'row_count': total_rows,
            'execution_time': execution_time,
            'query': user_query,
            'correction_note': correction_note,
            'corrected_entity': corrected_entity,
            'diagnosis': diagnosis,
            'query_type': query_type,
            'is_aggregate': is_aggregate,
            'drilldown_results': drilldown_results,
            'drilldown_columns': drilldown_cols,
            'drilldown_sql': drilldown_sql,
            'disambiguation': disambig_data
        })
        
    except Exception as e:
        execution_time = round(time.time() - start_time, 2)
        logger.error(f"[{request_id}] Search failed: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Search failed: {str(e)}',
            'execution_time': execution_time,
            'suggestions': get_suggested_queries()[:4]
        }), 500

@main.route('/', methods=['GET', 'POST'])
def home():
    """Home route"""
    results = None
    query = ''
    sql_query = ''
    error_message = None
    suggested_queries = get_suggested_queries()
    creds = get_azure_credentials(request)

    if request.method == 'POST':
        user_query = request.form.get('query', '').strip()
        if not user_query:
            error_message = "Please enter a search query."
        else:
            try:
                start_time = time.time()
                sql_query = generate_response(user_query, creds=creds)
                if not validate_sql_query(sql_query):
                    raise ValueError("Generated SQL query failed validation")
                
                results_raw, column_names = execute_sql_query(sql_query)
                total_rows = len(results_raw)
                if total_rows > 1000:
                    results_raw = results_raw[:1000]
                
                results = [dict(zip(column_names, row)) for row in results_raw]
            except Exception as e:
                error_message = f"Query failed: {str(e)}"
        query = user_query

    return render_template('index.html', 
                          results=results, 
                          query=query,
                          sql_query=sql_query,
                          error_message=error_message,
                          suggested_queries=suggested_queries)

@main.route('/api/suggestions', methods=['GET'])
def api_suggestions():
    """Query suggestions"""
    return jsonify({
        'suggestions': get_suggested_queries(),
        'status': 'success'
    })

@main.route('/api/validate', methods=['POST'])
def api_validate_query():
    """Query pre-validation"""
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    
    if not query or len(query) < 3:
        return jsonify({
            'valid': False,
            'message': 'Query is too short',
            'suggestions': get_suggested_queries()[:2]
        })
    
    return jsonify({'valid': True, 'message': 'Query is valid'})

@main.route('/api/execute', methods=['POST'])
def api_execute_query():
    """Direct SQL execution (restricted to development/testing environments)"""
    from flask import current_app
    admin_secret = os.getenv("ADMIN_SQL_SECRET")
    request_secret = request.headers.get("X-Admin-Secret")
    is_authorized = (
        current_app.debug
        or current_app.testing
        or (admin_secret and request_secret == admin_secret)
    )
    if not is_authorized:
        return jsonify({
            'status': 'error',
            'message': 'Direct SQL execution is disabled in production environments.'
        }), 403

    data = request.get_json(silent=True) or {}
    sql_query = data.get('query', '').strip()
    
    if not sql_query:
        return jsonify({'status': 'error', 'message': 'SQL query cannot be empty'}), 400
    
    try:
        if not validate_sql_query(sql_query):
            return jsonify({'status': 'error', 'message': 'Invalid or disallowed SQL query'}), 400
        
        # Execute with hard row ceiling (max 200) and 8s watchdog timeout to prevent OOM / DoS
        results, column_names = execute_sql_query(sql_query, max_rows=200, timeout_seconds=8.0)
        return jsonify({
            'status': 'success',
            'count': len(results),
            'results': [dict(zip(column_names, row)) for row in results]
        }), 200
    except TimeoutError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 504
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@main.route('/api/title_info', methods=['POST'])
def api_title_info():
    """Title details endpoint"""
    data = request.get_json() or {}
    title_id = data.get('title_id', '').strip()
    
    if not title_id:
        return jsonify({'status': 'error', 'message': 'Title ID is required'}), 400
    
    title_info = get_title_info(title_id)
    if not title_info:
        return jsonify({'status': 'error', 'message': 'Title not found'}), 404
        
    return jsonify({'status': 'success', 'title_info': title_info}), 200

@main.route('/api/generate_summary', methods=['POST'])
def api_generate_summary():
    """Generate title summary endpoint"""
    data = request.get_json() or {}
    title_name = data.get('title_name', '').strip()
    title_id = data.get('title_id', '').strip()
    creds = get_azure_credentials(request)
    
    if not title_name or not title_id:
        return jsonify({'success': False, 'error': 'Title name and ID are required'}), 400
    
    try:
        title_info = get_title_info(title_id)
        summary = generate_title_summary(title_name, title_info, creds=creds)
        return jsonify({
            'success': True,
            'title_name': title_name,
            'summary': summary
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/analytics/drilldown', methods=['POST'])
def api_analytics_drilldown():
    """
    High-speed targeted drilldown endpoint for analytical queries.
    Given base detail SQL and a filter value (e.g. year=2016),
    executes an optimized DuckDB query to retrieve exact title records.
    """
    try:
        data = request.get_json(silent=True) or {}
        base_sql = data.get('drilldown_sql', '').strip()
        filter_col = data.get('filter_col', 'premiered').strip()
        filter_val = data.get('filter_val')

        if not base_sql:
            return jsonify({'success': False, 'error': 'Missing drilldown SQL'}), 400

        if filter_val is None:
            return jsonify({'success': False, 'error': 'Missing filter value'}), 400

        # Clean base SQL
        sql_clean = base_sql.rstrip(';')
        sql_clean = re.sub(r'\s+LIMIT\s+\d+\s*$', '', sql_clean, flags=re.IGNORECASE)
        sql_clean = re.sub(r'\s+ORDER\s+BY\s+[\s\S]+?$', '', sql_clean, flags=re.IGNORECASE)

        # Build condition
        is_year = filter_col.lower() in ('year', 'premiered', 'release_year')
        if is_year or (isinstance(filter_val, str) and filter_val.strip().isdigit()) or isinstance(filter_val, (int, float)):
            target_col = 'premiered'
            condition = f"{target_col} = {int(filter_val)}"
        else:
            safe_str = str(filter_val).replace("'", "''")
            safe_col = 'genres' if 'genre' in filter_col.lower() else 'primary_title'
            condition = f"{safe_col} LIKE '%{safe_str}%'"

        targeted_sql = f"""
        WITH base_titles AS (
            {sql_clean}
        )
        SELECT * FROM base_titles
        WHERE {condition}
        ORDER BY votes DESC NULLS LAST, rating DESC NULLS LAST
        LIMIT 250;
        """

        if not validate_sql_query(targeted_sql):
            return jsonify({'success': False, 'error': 'Query validation failed'}), 400

        start_time = time.time()
        rows, cols = execute_sql_query(targeted_sql, max_rows=250)
        exec_time = round(time.time() - start_time, 3)

        results = [dict(zip(cols, row)) for row in rows]
        return jsonify({
            'success': True,
            'filter_col': filter_col,
            'filter_val': filter_val,
            'row_count': len(results),
            'execution_time': exec_time,
            'results': results,
            'columns': cols,
            'sql': targeted_sql
        })
    except Exception as e:
        logger.error(f"Drilldown query failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

