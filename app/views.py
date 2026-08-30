from flask import Blueprint, render_template, request, jsonify, has_request_context
import os
import sqlite3
import logging
import json
import time
import re
import threading
from openai import AzureOpenAI
import sys
from datetime import datetime
import uuid
import duckdb

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
    logger.error("Configuration file not found. Please copy config.template.py to config.py and fill in your API keys.")
    raise ImportError(
        "Configuration file missing. Please:\n"
        "1. Copy config.template.py to config.py\n"
        "2. Fill in your Azure OpenAI API credentials\n"
        "3. Restart the application"
    )

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
            try:
                body = req.get_json(silent=True) or {}
                if not h_key and body.get("api_key"):
                    api_key = body.get("api_key").strip()
                    is_custom = True
                if not h_endpoint and body.get("endpoint"):
                    endpoint = body.get("endpoint").strip()
                if not h_model and body.get("model"):
                    model = body.get("model").strip()
            except Exception:
                pass

    return {
        "api_key": api_key,
        "endpoint": endpoint,
        "api_version": api_version,
        "model": model,
        "is_custom": is_custom
    }

def get_azure_client(creds=None):
    """
    Returns the Azure OpenAI client and model name initialized with given credentials.
    """
    if creds is None:
        creds = get_azure_credentials(request if has_request_context() else None)
    
    if not creds["api_key"] or not creds["endpoint"]:
        raise ValueError("Azure OpenAI API Key or Endpoint is not configured. Please set it in config.py or in the UI settings.")

    client = AzureOpenAI(
        api_key=creds["api_key"],
        api_version=creds["api_version"],
        azure_endpoint=creds["endpoint"]
    )
    return client, creds["model"]

# Thread-safe DuckDB Connection Manager
_duckdb_lock = threading.Lock()
_duckdb_con = None
_views_initialized = False

def get_duckdb_database():
    """Get or initialize the shared in-process DuckDB connection with Azure Blob Storage views"""
    global _duckdb_con, _views_initialized
    with _duckdb_lock:
        if _duckdb_con is None:
            logger.info("Initializing in-memory DuckDB engine with Azure extension...")
            _duckdb_con = duckdb.connect(database=':memory:', read_only=False)
            _duckdb_con.execute("INSTALL azure; LOAD azure;")
            _duckdb_con.execute("INSTALL httpfs; LOAD httpfs;")
            
            if AZURE_STORAGE_CONNECTION_STRING:
                logger.info("Configuring DuckDB Azure Secret...")
                _duckdb_con.execute(f"""
                    CREATE SECRET IF NOT EXISTS (
                        TYPE AZURE,
                        CONNECTION_STRING '{AZURE_STORAGE_CONNECTION_STRING}'
                    );
                """)
                
        if not _views_initialized and AZURE_STORAGE_CONNECTION_STRING:
            container = AZURE_STORAGE_CONTAINER_NAME or 'imdb-data'
            tables = ['ratings', 'titles', 'people', 'crew', 'episodes', 'akas']
            for tbl in tables:
                blob_url = f"azure://{container}/{tbl}.parquet"
                try:
                    _duckdb_con.execute(f"CREATE OR REPLACE VIEW {tbl} AS SELECT * FROM '{blob_url}'")
                    logger.info(f"Initialized DuckDB view '{tbl}' -> {blob_url}")
                except Exception as e:
                    logger.warning(f"Could not initialize DuckDB view '{tbl}': {e}")
            _views_initialized = True
            
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
    """Post-process SQL to properly escape single quotes in string literals."""
    try:
        def fix_like_pattern(match):
            like_content = match.group(1)
            fixed_content = re.sub(r"(?<!')\'(?!\')", "''", like_content)
            return f"LIKE '{fixed_content}'"
        
        sql_query = re.sub(r"LIKE\s+'([^']*(?:'[^']*)*)'", fix_like_pattern, sql_query, flags=re.IGNORECASE)
        return sql_query
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
        response = client.chat.completions.create(
            model=model_name,
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
        
        response = client.chat.completions.create(
            model=model_name,
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

@main.route('/api/search', methods=['POST'])
def api_search():
    """AJAX search endpoint"""
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
        execution_time = round(time.time() - start_time, 2)
        total_rows = len(results)
        
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
            'query': user_query
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
