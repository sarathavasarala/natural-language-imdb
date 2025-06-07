from flask import Blueprint, render_template, request, jsonify
import os
import sqlite3
import logging
import json
import time
import re
from openai import AzureOpenAI
import sys
import os
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
    from config import AZURE_OPENAI_API_KEY, AZURE_OPENAI_API_VERSION, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_MODEL, DATABASE_PATH
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

def get_azure_client():
    """
    Returns the Azure OpenAI client initialized with necessary credentials.
    """
    return AzureOpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
        azure_endpoint=AZURE_OPENAI_ENDPOINT
    )

def generate_response(user_query):
    """
    Generate SQL query response using Azure OpenAI GPT-4.1 with enhanced prompt engineering
    """
    start_time = time.time()
    logger.info(f"Processing query: '{user_query}'")
    
    client = get_azure_client()
    
    # Enhanced system message with comprehensive examples and edge cases
    system_message = """
    You are an expert SQL query generator for IMDb database analysis. Your task is to convert natural language queries into precise SQLite queries.

    DATABASE SCHEMA:
    - people: person_id (VARCHAR), name (VARCHAR), born (INTEGER), died (INTEGER)
    - titles: title_id (VARCHAR), type (VARCHAR), primary_title (VARCHAR), original_title (VARCHAR), is_adult (INTEGER), premiered (INTEGER), ended (INTEGER), runtime_minutes (INTEGER), genres (VARCHAR)
    - akas: title_id (VARCHAR), title (VARCHAR), region (VARCHAR), language (VARCHAR), types (VARCHAR), attributes (VARCHAR), is_original_title (INTEGER)
    - crew: title_id (VARCHAR), person_id (VARCHAR), category (VARCHAR), job (VARCHAR), characters (VARCHAR)
    - episodes: episode_title_id (VARCHAR), show_title_id (VARCHAR), season_number (INTEGER), episode_number (INTEGER)
    - ratings: title_id (VARCHAR), rating (REAL), votes (INTEGER)

    CRITICAL: This is SQLite - do NOT use functions like PERCENTILE_CONT, PERCENTILE_DISC, or other advanced statistical functions that don't exist in SQLite.

    For percentile calculations in SQLite, use this pattern:
    WITH ordered_data AS (
        SELECT votes, ROW_NUMBER() OVER (ORDER BY votes) as rn, COUNT(*) OVER () as total_count
        FROM ratings
    )
    SELECT votes as percentile_40_votes
    FROM ordered_data 
    WHERE rn = CAST(0.4 * total_count AS INTEGER);

    IMPORTANT RULES:
    1. ALWAYS include ratings and votes when available
    2. Use proper JOINs for relationships
    3. Handle fuzzy name matching with LIKE '%name%'
    4. Include ORDER BY for better results (ratings DESC, premiered DESC, votes DESC)
    5. Handle plural/singular variations (movie/movies, actor/actors)
    6. Consider alternative titles in akas table for international searches
    7. Use ONLY SQLite-compatible functions and syntax

    ADVANCED EXAMPLES:

    Query: "Movies where Leonardo DiCaprio and Kate Winslet worked together"
    SQL: SELECT DISTINCT t.title_id, t.primary_title, t.premiered, t.genres, r.rating, r.votes 
         FROM titles t 
         JOIN crew c1 ON t.title_id = c1.title_id 
         JOIN crew c2 ON t.title_id = c2.title_id 
         JOIN people p1 ON c1.person_id = p1.person_id 
         JOIN people p2 ON c2.person_id = p2.person_id 
         LEFT JOIN ratings r ON t.title_id = r.title_id 
         WHERE p1.name LIKE '%Leonardo DiCaprio%' 
         AND p2.name LIKE '%Kate Winslet%' 
         AND t.type IN ('movie', 'tvMovie') 
         ORDER BY r.rating DESC, r.votes DESC;

    Query: "Highest rated sci-fi movies from 2010s"
    SQL: SELECT t.title_id, t.primary_title, t.premiered, t.genres, r.rating, r.votes 
         FROM titles t 
         JOIN ratings r ON t.title_id = r.title_id 
         WHERE t.type IN ('movie', 'tvMovie') 
         AND t.genres LIKE '%Sci-Fi%' 
         AND t.premiered BETWEEN 2010 AND 2019 
         AND r.votes >= 1000 
         ORDER BY r.rating DESC, r.votes DESC;

    Query: "Movies with 40th percentile votes but high ratings"
    SQL: WITH vote_percentile AS (
         SELECT votes, ROW_NUMBER() OVER (ORDER BY votes) as rn, COUNT(*) OVER () as total_count
         FROM ratings
         ),
         percentile_40_votes AS (
         SELECT votes as target_votes FROM vote_percentile 
         WHERE rn = CAST(0.4 * total_count AS INTEGER)
         )
         SELECT t.title_id, t.primary_title, t.premiered, t.genres, r.rating, r.votes 
         FROM titles t 
         JOIN ratings r ON t.title_id = r.title_id 
         CROSS JOIN percentile_40_votes p
         WHERE t.type IN ('movie', 'tvMovie') 
         AND r.votes <= p.target_votes 
         AND r.rating > 7.0 
         ORDER BY r.rating DESC;

    Query: "Directors who made both horror and comedy movies"
    SQL: SELECT p.name, p.person_id,
         COUNT(CASE WHEN t.genres LIKE '%Horror%' THEN 1 END) as horror_count,
         COUNT(CASE WHEN t.genres LIKE '%Comedy%' THEN 1 END) as comedy_count,
         AVG(r.rating) as avg_rating
         FROM people p 
         JOIN crew c ON p.person_id = c.person_id 
         JOIN titles t ON c.title_id = t.title_id 
         LEFT JOIN ratings r ON t.title_id = r.title_id 
         WHERE c.category = 'director' 
         AND t.type IN ('movie', 'tvMovie') 
         AND (t.genres LIKE '%Horror%' OR t.genres LIKE '%Comedy%') 
         GROUP BY p.person_id, p.name 
         HAVING horror_count > 0 AND comedy_count > 0 
         ORDER BY avg_rating DESC;

    GENRE MAPPING: Use these exact genre names from IMDb:
    Action, Adventure, Animation, Biography, Comedy, Crime, Documentary, Drama, Family, Fantasy, Film-Noir, History, Horror, Music, Musical, Mystery, Romance, Sci-Fi, Sport, Thriller, War, Western

    PERSON CATEGORY MAPPING:
    - actor, actress → use 'actor' or both
    - director → 'director'
    - writer → 'writer'
    - producer → 'producer'
    - composer → 'composer'

    Return ONLY the SQL query without markdown formatting or explanations.
    """
    
    try:
        response = client.chat.completions.create(
            model=AZURE_OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_query}
            ],
            temperature=0.3,  # Lower temperature for more consistent SQL
            max_tokens=800,
            top_p=0.9
        )
        
        sql_query = response.choices[0].message.content.strip()
        
        # Clean up the SQL query
        sql_query = re.sub(r'^```sql\s*', '', sql_query, flags=re.IGNORECASE)
        sql_query = re.sub(r'^```\s*', '', sql_query)
        sql_query = re.sub(r'\s*```$', '', sql_query)
        sql_query = sql_query.strip()
        
        processing_time = time.time() - start_time
        logger.info(f"Generated SQL in {processing_time:.2f}s: {sql_query[:100]}...")
        
        return sql_query
        
    except Exception as e:
        logger.error(f"Error generating SQL: {str(e)}")
        raise

@main.route('/', methods=['GET', 'POST'])
def home():
    """Enhanced home route with comprehensive logging and error handling"""
    results = None
    query = ''
    sql_query = ''
    error_message = None
    suggested_queries = get_suggested_queries()

    if request.method == 'POST':
        user_query = request.form.get('query', '').strip()
        logger.info(f"Received user query: '{user_query}' from IP: {request.remote_addr}")
        
        if not user_query:
            error_message = "Please enter a search query."
            logger.warning("Empty query submitted")
        else:
            try:
                # Generate SQL query
                start_time = time.time()
                sql_query = generate_response(user_query)
                
                # Validate SQL query
                if not validate_sql_query(sql_query):
                    raise ValueError("Generated SQL query failed validation")
                
                # Execute query
                results, column_names = execute_sql_query(sql_query)
                execution_time = time.time() - start_time
                
                if results:
                    results = [dict(zip(column_names, row)) for row in results]
                    logger.info(f"Query successful: {len(results)} results in {execution_time:.2f}s")
                else:
                    logger.info("Query executed successfully but returned no results")
                    
            except Exception as e:
                error_message = f"Query failed: {str(e)}"
                logger.error(f"Query execution failed: {str(e)}", exc_info=True)
        
        query = user_query

    return render_template('index.html', 
                         results=results, 
                         query=query,
                         sql_query=sql_query,
                         error_message=error_message,
                         suggested_queries=suggested_queries)


# API Routes for dynamic features
@main.route('/api/suggestions', methods=['GET'])
def api_suggestions():
    """API endpoint to get query suggestions"""
    suggestions = get_suggested_queries()
    return jsonify({
        'suggestions': suggestions,
        'status': 'success'
    })

@main.route('/api/validate', methods=['POST'])
def api_validate_query():
    """API endpoint to validate queries before submission"""
    data = request.get_json()
    query = data.get('query', '').strip()
    
    if not query:
        return jsonify({
            'valid': False,
            'message': 'Query cannot be empty',
            'suggestions': ['Try: "Movies with Tom Hanks"', 'Try: "Highest rated sci-fi movies"']
        })
    
    if len(query) < 5:
        return jsonify({
            'valid': False,
            'message': 'Query seems too short. Please be more specific.',
            'suggestions': [f'Try: "{query} movies"', f'Try: "Best {query} films"']
        })
    
    return jsonify({
        'valid': True,
        'message': 'Query looks good!',
        'estimated_results': 'Analyzing...'
    })


@main.route('/api/filter-options')
def get_filter_options():
    """API endpoint to get filter options for the UI"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        
        # Get year range
        c.execute("SELECT MIN(premiered) as min_year, MAX(premiered) as max_year FROM titles WHERE premiered IS NOT NULL AND premiered > 1800")
        year_range = c.fetchone()
        
        # Get rating range
        c.execute("SELECT MIN(CAST(rating AS REAL)/10.0) as min_rating, MAX(CAST(rating AS REAL)/10.0) as max_rating FROM ratings WHERE rating IS NOT NULL")
        rating_range = c.fetchone()
        
        # Get votes range
        c.execute("SELECT MIN(votes) as min_votes, MAX(votes) as max_votes FROM ratings WHERE votes IS NOT NULL")
        votes_range = c.fetchone()
        
        # Get unique genres
        c.execute("SELECT DISTINCT genres FROM titles WHERE genres IS NOT NULL AND genres != '' AND genres != 'N'")
        genre_results = c.fetchall()
        
        # Parse genres (they are comma-separated)
        all_genres = set()
        for (genres_str,) in genre_results:
            if genres_str:
                for genre in genres_str.split(','):
                    all_genres.add(genre.strip())
        
        # Get title types
        c.execute("SELECT DISTINCT type FROM titles WHERE type IS NOT NULL ORDER BY type")
        types = [row[0] for row in c.fetchall()]
        
        conn.close()
        
        return jsonify({
            'years': {
                'min': year_range[0] or 1900,
                'max': year_range[1] or 2024
            },
            'ratings': {
                'min': rating_range[0] or 1,
                'max': rating_range[1] or 10
            },
            'votes': {
                'min': votes_range[0] or 1,
                'max': votes_range[1] or 1000000
            },
            'genres': sorted(list(all_genres)),
            'types': types
        })
        
    except Exception as e:
        logger.error(f"Error getting filter options: {str(e)}")
        return jsonify({'error': str(e)}), 500

@main.route('/api/filtered-search', methods=['POST'])
def filtered_search():
    """API endpoint for filtered search"""
    try:
        data = request.get_json()
        
        # Build SQL query based on filters
        base_query = """
        SELECT DISTINCT t.title_id, t.primary_title, t.type, t.premiered, t.genres, 
               t.runtime_minutes, CAST(r.rating AS REAL)/10.0 as rating, r.votes
        FROM titles t
        LEFT JOIN ratings r ON t.title_id = r.title_id
        WHERE 1=1
        """
        
        conditions = []
        params = []
        
        # Year filter
        if data.get('yearMin') and data.get('yearMax'):
            conditions.append("t.premiered BETWEEN ? AND ?")
            params.extend([data['yearMin'], data['yearMax']])
        
        # Rating filter
        if data.get('ratingMin') and data.get('ratingMax'):
            conditions.append("CAST(r.rating AS REAL)/10.0 BETWEEN ? AND ?")
            params.extend([data['ratingMin'], data['ratingMax']])
        
        # Votes filter
        if data.get('votesMin') and data.get('votesMax'):
            conditions.append("r.votes BETWEEN ? AND ?")
            params.extend([data['votesMin'], data['votesMax']])
        
        # Genre filter
        if data.get('genres') and len(data['genres']) > 0:
            genre_conditions = []
            for genre in data['genres']:
                genre_conditions.append("t.genres LIKE ?")
                params.append(f"%{genre}%")
            conditions.append(f"({' OR '.join(genre_conditions)})")
        
        # Type filter
        if data.get('types') and len(data['types']) > 0:
            type_placeholders = ','.join(['?' for _ in data['types']])
            conditions.append(f"t.type IN ({type_placeholders})")
            params.extend(data['types'])
        
        # Text search filter
        if data.get('searchText'):
            conditions.append("t.primary_title LIKE ?")
            params.append(f"%{data['searchText']}%")
        
        # Add conditions to query
        if conditions:
            base_query += " AND " + " AND ".join(conditions)
        
        # Add ordering and limit
        base_query += " ORDER BY CAST(r.rating AS REAL)/10.0 DESC, r.votes DESC, t.premiered DESC LIMIT 1000"
        
        # Execute query with parameters
        conn = sqlite3.connect(DATABASE_PATH, timeout=30.0)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("PRAGMA query_only = ON")
        c.execute("PRAGMA cache_size = 10000")
        
        start_time = time.time()
        logger.info(f"Executing query with params: {params}")
        c.execute(base_query, params)
        results = c.fetchall()
        execution_time = time.time() - start_time
        
        columns = [description[0] for description in c.description] if c.description else []
        conn.close()
        
        logger.info(f"Filtered search executed in {execution_time:.2f}s: {len(results)} rows returned")
        
        # Convert results to list of dictionaries
        results_list = []
        for row in results:
            row_dict = {}
            for i, col in enumerate(columns):
                row_dict[col] = row[i]
            results_list.append(row_dict)
        
        return jsonify({
            'results': results_list,
            'count': len(results_list),
            'sql_query': base_query
        })
        
    except Exception as e:
        logger.error(f"Error in filtered search: {str(e)}")
        return jsonify({'error': str(e)}), 500


def get_suggested_queries():
    """Return a list of suggested example queries"""
    return [
        {
            "text": "Movies where Robert De Niro and Al Pacino worked together",
            "category": "Collaborations"
        },
        {
            "text": "Highest rated sci-fi movies from the 2010s",
            "category": "Genre & Era"
        },
        {
            "text": "Christopher Nolan's movies ordered by rating",
            "category": "Director Focus"
        },
        {
            "text": "TV shows with more than 10 seasons",
            "category": "Television"
        },
        {
            "text": "Directors who made both horror and comedy movies",
            "category": "Multi-Genre"
        },
        {
            "text": "Most popular actors in Marvel movies",
            "category": "Franchise"
        }
    ]


def validate_sql_query(sql_query):
    """Validate the generated SQL query for security only - keep it minimal"""
    if not sql_query:
        return False
    
    # Only check for destructive operations - let database handle syntax/function errors
    dangerous_keywords = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE', 'TRUNCATE']
    sql_upper = sql_query.upper()
    
    for keyword in dangerous_keywords:
        if keyword in sql_upper:
            logger.warning(f"Dangerous SQL keyword detected: {keyword}")
            return False
    
    return True


def execute_sql_query(sql_query, db_path=None):
    """
    Execute SQL query with comprehensive error handling and logging
    """
    if db_path is None:
        db_path = DATABASE_PATH
    
    logger.info(f"Executing SQL: {sql_query[:200]}{'...' if len(sql_query) > 200 else ''}")
    
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        c = conn.cursor()
        
        # Set query timeout and other pragmas for better performance
        c.execute("PRAGMA query_only = ON")  # Read-only mode for security
        c.execute("PRAGMA cache_size = 10000")  # Increase cache size
        
        start_time = time.time()
        c.execute(sql_query)
        results = c.fetchall()
        execution_time = time.time() - start_time
        
        column_names = [description[0] for description in c.description] if c.description else []
        
        logger.info(f"SQL executed successfully in {execution_time:.2f}s: {len(results)} rows returned")
        
        conn.close()
        return results, column_names
        
    except sqlite3.Error as e:
        error_msg = f"Database error: {str(e)}"
        logger.error(f"SQL execution failed: {error_msg}")
        logger.error(f"Failed SQL: {sql_query}")
        if 'conn' in locals():
            conn.close()
        raise Exception(error_msg)
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"Unexpected error during SQL execution: {error_msg}")
        if 'conn' in locals():
            conn.close()
        raise Exception(error_msg)

