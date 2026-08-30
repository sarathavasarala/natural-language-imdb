from flask import Blueprint, render_template, request, jsonify, has_request_context, Response, stream_with_context
import os
import sqlite3
import logging
import json
import time
import re
import threading
import fcntl
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
- titles: title_id (VARCHAR), type (VARCHAR), primary_title (VARCHAR), original_title (VARCHAR), is_adult (INTEGER), premiered (INTEGER), ended (INTEGER), runtime_minutes (INTEGER), genres (VARCHAR)
- akas: title_id (VARCHAR), title (VARCHAR), region (VARCHAR), language (VARCHAR), types (VARCHAR), attributes (VARCHAR), is_original_title (INTEGER)
- crew: title_id (VARCHAR), person_id (VARCHAR), category (VARCHAR), job (VARCHAR), characters (VARCHAR)
- episodes: episode_title_id (VARCHAR), show_title_id (VARCHAR), season_number (INTEGER), episode_number (INTEGER)
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

    # 1. Direct Foundry / OpenAI-compatible v1 router
    if "/openai/v1" in endpoint or "/v1" in endpoint or "/models" in endpoint:
        logger.info(f"Connecting via OpenAI v1 router to Foundry endpoint: {endpoint}")
        client = OpenAI(
            base_url=endpoint,
            api_key=api_key
        )
        return client, model

    # 2. Foundry domain without /openai/v1 suffix
    if "services.ai.azure.com" in endpoint:
        foundry_v1_url = f"{endpoint}/openai/v1"
        logger.info(f"Connecting via Foundry services.ai.azure.com router: {foundry_v1_url}")
        client = OpenAI(
            base_url=foundry_v1_url,
            api_key=api_key
        )
        return client, model

    # 3. Classic Azure OpenAI (.openai.azure.com or .cognitiveservices.azure.com)
    clean_endpoint = re.sub(r'/openai.*$', '', endpoint)
    logger.info(f"Connecting via AzureOpenAI client to endpoint: {clean_endpoint}")
    client = AzureOpenAI(
        azure_endpoint=clean_endpoint,
        api_version=api_version,
        api_key=api_key
    )
    return client, model

# Thread-safe DuckDB Connection Manager
_duckdb_lock = threading.Lock()
_duckdb_con = None
DUCKDB_BLOB_NAME = os.getenv("DUCKDB_BLOB_NAME", "imdb.duckdb")
DUCKDB_DATABASE_PATH = os.getenv(
    "DUCKDB_DATABASE_PATH",
    "/home/data/imdb.duckdb" if os.getenv("WEBSITE_SITE_NAME") else "db/imdb.duckdb"
)

def _local_database_is_current(database_path, etag):
    etag_path = f"{database_path}.etag"
    if not os.path.exists(database_path) or not os.path.exists(etag_path):
        return False
    with open(etag_path, "r", encoding="utf-8") as etag_file:
        return etag_file.read().strip() == etag


def ensure_local_duckdb_database():
    """Download the immutable DuckDB artifact to persistent local storage when needed."""
    database_path = os.path.abspath(DUCKDB_DATABASE_PATH)
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

def execute_sql_query(sql_query):
    """Execute SQL query and return results with column names"""
    cursor = None
    try:
        logger.info(f"Executing SQL: {sql_query[:200]}...")
        cursor = get_database_connection()
        cursor.execute(sql_query)
        
        # Get column names
        column_names = [description[0] for description in cursor.description] if cursor.description else []
        
        # Fetch results
        results = cursor.fetchall()
        logger.info(f"Query executed successfully, returned {len(results)} rows")
        
        return results, column_names
        
    except Exception as e:
        logger.error(f"SQL execution error: {str(e)}")
        raise
    finally:
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

def validate_sql_query(sql_query):
    """Basic validation of SQL query for security and syntax"""
    try:
        sql_lower = sql_query.lower().strip()
        
        dangerous_patterns = ['drop', 'delete', 'update', 'insert', 'alter', 'create', 'truncate']
        for pattern in dangerous_patterns:
            # Check for standalone keywords
            if re.search(r'\b' + pattern + r'\b', sql_lower):
                logger.warning(f"Potentially dangerous SQL operation detected: {pattern}")
                return False
        
        if not sql_lower.startswith('select') and not sql_lower.startswith('with'):
            logger.warning("SQL query must be a SELECT or WITH statement")
            return False
        
        # Syntax validation using EXPLAIN
        cursor = get_database_connection()
        cursor.execute(f"EXPLAIN {sql_query}")
        return True
    except Exception as e:
        logger.warning(f"SQL syntax validation failed: {str(e)}")
        return False

def extract_filter_literals(sql_query, user_query=""):
    """
    Extract string literals from SQL WHERE clauses and natural language user query.
    """
    literals = set()
    
    # Extract string literals in SQL (e.g., = 'foo' or LIKE '%foo%' or ILIKE '%foo%')
    sql_matches = re.findall(r"(?:=\s*'([^']+)'|LIKE\s*'([^']+)'|ILIKE\s*'([^']+)')", sql_query, flags=re.IGNORECASE)
    for group in sql_matches:
        for match in group:
            if match:
                cleaned = match.replace('%', '').strip()
                if len(cleaned) >= 2 and cleaned.lower() not in (
                    'movie', 'tvmovie', 'tvseries', 'short', 'tvepisode', 'video',
                    'actor', 'actress', 'director', 'writer', 'producer', 'self', 'archive_footage'
                ):
                    literals.add(cleaned)

    if user_query:
        quoted = re.findall(r'["\']([^"\']+)["\']', user_query)
        for q in quoted:
            if len(q.strip()) >= 2:
                literals.add(q.strip())

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

    response = client.responses.create(**kwargs)
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
    return "chat completion" in error_text and any(
        phrase in error_text
        for phrase in ("not supported", "not allowed", "unsupported", "responses api")
    )


def safe_chat_completion(client, model_name, messages, temperature=None, response_format=None):
    """
    Executes chat completion with fallback for models that enforce temperature=1 / no custom temperature
    (e.g., gpt-5.6-luna, reasoning models, OpenAI o-series) or use the responses API.
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
        
    while True:
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as error:
            error_text = str(error).lower()
            if "temperature" in error_text and "temperature" in kwargs:
                logger.info(f"Retrying chat completion without temperature for model {model_name}")
                kwargs.pop("temperature")
                continue
            if "response_format" in error_text and "response_format" in kwargs:
                logger.info(f"Retrying chat completion without response_format for model {model_name}")
                kwargs.pop("response_format")
                continue
            if hasattr(client, "responses") and _should_use_responses_fallback(error):
                logger.info(f"Chat Completions unavailable for {model_name}; using Responses API")
                return _responses_api_completion(client, model_name, messages)
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
            probe_summary_lines.append(f"- Entity '{lit}': Exactly matched Person '{pdata.get('exact_person_name')}'.")
        elif pdata.get("person_fuzzy"):
            top_sug = pdata["person_fuzzy"][0]
            probe_summary_lines.append(f"- Entity '{lit}': NOT found in people. Top fuzzy match in database is '{top_sug['name']}' (similarity: {top_sug['similarity']}).")
        
        if pdata.get("title_exact"):
            probe_summary_lines.append(f"- Entity '{lit}': Exactly matched Title '{pdata.get('exact_title_name')}'.")
        elif pdata.get("title_fuzzy"):
            top_sug = pdata["title_fuzzy"][0]
            probe_summary_lines.append(f"- Entity '{lit}': NOT found in titles. Top fuzzy match in database is '{top_sug['title']}' (similarity: {top_sug['similarity']}).")

        if not pdata.get("person_exact") and not pdata.get("person_fuzzy") and not pdata.get("title_exact") and not pdata.get("title_fuzzy"):
            probe_summary_lines.append(f"- Entity '{lit}': Not found in people or titles (no close match).")

    probe_context = "\n".join(probe_summary_lines) if probe_summary_lines else "No specific entities extracted."

    system_prompt = f"""
You are an expert IMDb text-to-SQL diagnostic agent.
A user executed a natural language search query, but the generated SQL query returned 0 results from the IMDb database.

DATABASE SCHEMA:
{DB_SCHEMA_PROMPT}

DATABASE PROBE EVIDENCE:
{probe_context}

YOUR TASK:
Analyze whether this was caused by:
1. "MISSPELLED_ENTITY": A typo or misspelling in person names or titles (e.g. 'gorge clooney' -> 'George Clooney'). Use the verified fuzzy matches from the database evidence!
2. "OVERLY_STRICT_FILTER": The entity exists, but overly strict WHERE constraints (e.g. exact release year, rating threshold > 9.9, or specific genre) produced 0 rows.
3. "GENUINE_EMPTY": The entity was found or verified, but no matching cinema records legitimately exist for that combination (e.g. Tom Hanks has no 1975 sci-fi movies). DO NOT invent fictional data or substitute unrelated actors.

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
        data = json.loads(content)
        
        if data.get("corrected_sql"):
            sql = data["corrected_sql"]
            sql = re.sub(r'^```sql\s*', '', sql, flags=re.IGNORECASE)
            sql = re.sub(r'^```\s*', '', sql)
            sql = re.sub(r'\s*```$', '', sql)
            data["corrected_sql"] = fix_single_quotes_in_sql(sql.strip())
            
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
    You are an expert SQL query generator for IMDb database analysis. Your task is to convert natural language queries into precise standard SQL queries.

    {DB_SCHEMA_PROMPT}

    AVOIDING DUPLICATES:
    - ALWAYS use SELECT DISTINCT when joining tables, especially with crew/people tables
    - When multiple crew members are involved, use proper subqueries or GROUP BY with aggregation
    - Be extra careful with queries involving actors, directors, or multiple people relationships

    IMPORTANT RULES:
    1. ALWAYS use SELECT DISTINCT to prevent duplicate results from JOINs
    2. ALWAYS include ratings and votes when available
    3. Use proper JOINs for relationships
    4. For name searches: Try exact match first, then LIKE as fallback
    5. For crew queries: Filter by category early (actor, actress, director, etc.)
    6. For title queries: Filter by type early (movie, tvMovie, tvSeries, etc.)
    7. Include ORDER BY for better results (ratings DESC, premiered DESC, votes DESC)
    8. Limit results when appropriate to prevent overly large returns
    9. ESCAPE SINGLE QUOTES: Replace single quotes (') with double single quotes ('') in names (e.g., O'Brien becomes O''Brien)

    INDEX-OPTIMIZED EXAMPLES:

    Query: "Movies with Jim Carrey rated above 7"
    SQL: SELECT DISTINCT t.title_id, t.primary_title, t.premiered, t.genres, r.rating, r.votes 
         FROM people p 
         JOIN crew c ON p.person_id = c.person_id 
         JOIN titles t ON c.title_id = t.title_id 
         JOIN ratings r ON t.title_id = r.title_id 
         WHERE p.name = 'Jim Carrey'
         AND c.category IN ('actor', 'actress')
         AND t.type IN ('movie', 'tvMovie') 
         AND r.rating > 7.0 
         ORDER BY r.rating DESC, r.votes DESC;

    Query: "Highest rated sci-fi movies from 2010s"
    SQL: SELECT DISTINCT t.title_id, t.primary_title, t.premiered, t.genres, r.rating, r.votes 
         FROM titles t 
         JOIN ratings r ON t.title_id = r.title_id 
         WHERE t.type IN ('movie', 'tvMovie') 
         AND t.premiered BETWEEN 2010 AND 2019
         AND t.genres LIKE '%Sci-Fi%' 
         AND r.votes >= 1000 
         ORDER BY r.rating DESC, r.votes DESC;

    Return ONLY the SQL query without markdown formatting or explanations.
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
        
        sql_query = fix_single_quotes_in_sql(sql_query)
        
        processing_time = time.time() - start_time
        logger.info(f"Generated SQL in {processing_time:.2f}s: {sql_query[:100]}...")
        
        return sql_query
        
    except Exception as e:
        logger.error(f"Error generating SQL: {str(e)}")
        raise

def get_suggested_queries():
    """Return a list of suggested example queries"""
    return [
        "Movies with Tom Hanks",
        "Highest rated sci-fi movies from 2010s", 
        "Christopher Nolan movies",
        "Movies where Leonardo DiCaprio and Kate Winslet worked together",
        "Best movies from 2020",
        "Directors who made both horror and comedy movies",
        "Draw a chart of Tom Hanks movies by year",
        "Show genre distribution of top 100 movies"
    ]

def get_title_info(title_id):
    """Get detailed information about a specific title"""
    try:
        cursor = get_database_connection()
        query = f"""
        SELECT t.title_id, t.primary_title, t.original_title, t.premiered, t.ended, 
               t.runtime_minutes, t.genres, t.type, r.rating, r.votes
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

        # Step 1: Understanding query
        yield f"data: {json.dumps({'type': 'status', 'stage': 'generating', 'message': 'Understanding your question...'})}\n\n"
        
        try:
            sql_query = generate_response(user_query, creds=creds)
        except Exception as e:
            logger.error(f"[{request_id}] Query interpretation failed: {e}")
            yield f"data: {json.dumps({'type': 'error', 'error': f'Could not interpret search: {str(e)}', 'suggestions': get_suggested_queries()[:4]})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'sql', 'stage': 'sql_ready', 'sql': sql_query, 'attempt': 1})}\n\n"

        # Validate query
        if not validate_sql_query(sql_query):
            yield f"data: {json.dumps({'type': 'status', 'stage': 'refining', 'message': 'Refining search criteria...'})}\n\n"
            try:
                retry_query = f"Simple query: {user_query}. Return only a standard SELECT with JOINs, no subqueries."
                sql_query = generate_response(retry_query, creds=creds)
            except Exception as e:
                pass

            if not validate_sql_query(sql_query):
                yield f"data: {json.dumps({'type': 'error', 'error': 'Could not process this query. Try rephrasing with simpler keywords.', 'sql_query': sql_query, 'suggestions': get_suggested_queries()[:4]})}\n\n"
                return

        # Step 2: Searching database
        yield f"data: {json.dumps({'type': 'status', 'stage': 'executing', 'message': 'Searching across 10M+ movies, shows & cast...'})}\n\n"

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
            logger.info(f"[{request_id}] Search success: {total_rows} rows in {execution_time}s")
            yield f"data: {json.dumps({'type': 'result', 'success': True, 'results': results_dicts, 'column_names': column_names, 'sql_query': sql_query, 'row_count': total_rows, 'execution_time': execution_time, 'query': user_query, 'stage': 'completed'})}\n\n"
            return

        # Step 3: 0 rows returned -> Check for typos / intent matching
        yield f"data: {json.dumps({'type': 'status', 'stage': 'probing', 'message': 'Checking database for alternate spellings and matches...'})}\n\n"

        literals = extract_filter_literals(sql_query, user_query)
        probe_data = probe_duckdb_entities(literals)

        yield f"data: {json.dumps({'type': 'status', 'stage': 'reflecting', 'message': 'Matching closely related titles & cast members...'})}\n\n"

        reflection = reflect_on_zero_results(user_query, sql_query, probe_data, creds=creds)
        diagnosis = reflection.get("diagnosis", "GENUINE_EMPTY")
        explanation = reflection.get("explanation", "No matching records found.")
        corrected_sql = reflection.get("corrected_sql")
        corrected_entity = reflection.get("corrected_entity")

        if diagnosis in ("MISSPELLED_ENTITY", "OVERLY_STRICT_FILTER") and corrected_sql and validate_sql_query(corrected_sql):
            yield f"data: {json.dumps({'type': 'retry', 'stage': 'retrying', 'message': explanation, 'corrected_entity': corrected_entity, 'new_sql': corrected_sql, 'attempt': 2})}\n\n"
            try:
                retry_results, retry_cols = execute_sql_query(corrected_sql)
                retry_rows = len(retry_results)
                execution_time = round(time.time() - start_time, 2)
                
                if retry_rows > 0:
                    if retry_rows > 1000:
                        retry_results = retry_results[:1000]
                    retry_dicts = [dict(zip(retry_cols, row)) for row in retry_results]
                    logger.info(f"[{request_id}] Auto-corrected search success: {retry_rows} rows in {execution_time}s")
                    yield f"data: {json.dumps({'type': 'result', 'success': True, 'results': retry_dicts, 'column_names': retry_cols, 'sql_query': corrected_sql, 'original_sql': sql_query, 'row_count': retry_rows, 'execution_time': execution_time, 'correction_note': explanation, 'corrected_entity': corrected_entity, 'diagnosis': diagnosis, 'query': user_query, 'stage': 'completed'})}\n\n"
                    return
            except Exception as e:
                logger.warning(f"[{request_id}] Re-query failed: {e}")

        # If still 0 results or genuine empty
        execution_time = round(time.time() - start_time, 2)
        yield f"data: {json.dumps({'type': 'result', 'success': True, 'results': [], 'column_names': column_names, 'sql_query': sql_query, 'row_count': 0, 'execution_time': execution_time, 'explanation': explanation, 'diagnosis': diagnosis, 'query': user_query, 'stage': 'completed'})}\n\n"

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
            retry_query = f"Simple query: {user_query}. Return only a standard SELECT with JOINs, no subqueries."
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
        logger.info(f"[{request_id}] Search returned {total_rows} rows in {execution_time}s")
        
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
            'diagnosis': diagnosis
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
    """Direct SQL execution (admin/testing)"""
    data = request.get_json() or {}
    sql_query = data.get('query', '').strip()
    
    if not sql_query:
        return jsonify({'status': 'error', 'message': 'SQL query cannot be empty'}), 400
    
    try:
        if not validate_sql_query(sql_query):
            return jsonify({'status': 'error', 'message': 'Invalid or disallowed SQL query'}), 400
        
        results, column_names = execute_sql_query(sql_query)
        return jsonify({
            'status': 'success',
            'results': [dict(zip(column_names, row)) for row in results]
        }), 200
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
