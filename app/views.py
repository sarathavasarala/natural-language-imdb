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

def fix_single_quotes_in_sql(sql_query):
    """
    Post-process SQL to properly escape single quotes in string literals.
    This is a safety net for cases where the AI doesn't properly escape quotes.
    """
    try:
        # Pattern to find LIKE '%...%' patterns that might contain unescaped single quotes
        # This regex looks for LIKE patterns and fixes single quotes within them
        def fix_like_pattern(match):
            like_content = match.group(1)
            # Replace single quotes with double single quotes, but avoid double-escaping
            fixed_content = re.sub(r"(?<!')\'(?!\')", "''", like_content)
            return f"LIKE '{fixed_content}'"
        
        # Apply the fix to LIKE patterns
        sql_query = re.sub(r"LIKE\s+'([^']*(?:'[^']*)*)'", fix_like_pattern, sql_query, flags=re.IGNORECASE)
        
        logger.info(f"SQL quote fixing applied")
        return sql_query
    except Exception as e:
        logger.warning(f"Error in SQL quote fixing: {str(e)}, returning original query")
        return sql_query

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

    AVOIDING DUPLICATES:
    - ALWAYS use SELECT DISTINCT when joining tables, especially with crew/people tables
    - When multiple crew members are involved, use proper subqueries or GROUP BY with aggregation
    - Be extra careful with queries involving actors, directors, or multiple people relationships

    IMPORTANT RULES:
    1. ALWAYS use SELECT DISTINCT to prevent duplicate results from JOINs
    2. ALWAYS include ratings and votes when available
    3. Use proper JOINs for relationships
    4. OPTIMIZE for existing indices: Put most selective filters first in WHERE clause
    5. For name searches: Try exact match first (uses ix_people_name index), then LIKE as fallback
    6. For crew queries: Filter by category early (uses ix_crew_category index)
    7. For title queries: Filter by type early (uses ix_titles_type index)
    8. Include ORDER BY for better results (ratings DESC, premiered DESC, votes DESC)
    9. Handle plural/singular variations (movie/movies, actor/actors)
    10. Consider alternative titles in akas table for international searches
    11. Use ONLY SQLite-compatible functions and syntax
    12. ESCAPE SINGLE QUOTES: Replace single quotes (') with double single quotes ('') in names (e.g., O'Brien becomes O''Brien)

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

    Query: "Find actor by partial name (when exact name unknown)"
    SQL: SELECT DISTINCT t.title_id, t.primary_title, t.premiered, t.genres, r.rating, r.votes 
         FROM people p 
         JOIN crew c ON p.person_id = c.person_id 
         JOIN titles t ON c.title_id = t.title_id 
         LEFT JOIN ratings r ON t.title_id = r.title_id 
         WHERE (p.name = 'Tom Hanks' OR p.name LIKE 'Tom Hanks%' OR p.name LIKE '%Tom Hanks')
         AND c.category IN ('actor', 'actress')
         AND t.type IN ('movie', 'tvMovie') 
         ORDER BY r.rating DESC, r.votes DESC;

    Query: "Movies where Leonardo DiCaprio and Kate Winslet worked together"
    SQL: SELECT DISTINCT t.title_id, t.primary_title, t.premiered, t.genres, r.rating, r.votes 
         FROM people p1 
         JOIN crew c1 ON p1.person_id = c1.person_id 
         JOIN titles t ON c1.title_id = t.title_id 
         JOIN crew c2 ON t.title_id = c2.title_id 
         JOIN people p2 ON c2.person_id = p2.person_id 
         JOIN ratings r ON t.title_id = r.title_id 
         WHERE p1.name = 'Leonardo DiCaprio'
         AND p2.name = 'Kate Winslet'
         AND c1.category IN ('actor', 'actress')
         AND c2.category IN ('actor', 'actress')
         AND t.type IN ('movie', 'tvMovie') 
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

    Query: "Movies with Conan O'Brien"
    SQL: SELECT DISTINCT t.title_id, t.primary_title, t.premiered, t.genres, r.rating, r.votes 
         FROM people p 
         JOIN crew c ON p.person_id = c.person_id 
         JOIN titles t ON c.title_id = t.title_id 
         LEFT JOIN ratings r ON t.title_id = r.title_id 
         WHERE p.name = 'Conan O''Brien'
         AND t.type IN ('movie', 'tvMovie') 
         ORDER BY r.rating DESC, r.votes DESC;

    Query: "Directors who made both horror and comedy movies"
    SQL: SELECT DISTINCT p.name, p.person_id,
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

    Query: "Christopher Nolan movies"
    SQL: SELECT DISTINCT t.title_id, t.primary_title, t.premiered, t.genres, r.rating, r.votes 
         FROM people p 
         JOIN crew c ON p.person_id = c.person_id 
         JOIN titles t ON c.title_id = t.title_id 
         LEFT JOIN ratings r ON t.title_id = r.title_id 
         WHERE p.name = 'Christopher Nolan'
         AND c.category = 'director'
         AND t.type IN ('movie', 'tvMovie') 
         ORDER BY r.rating DESC, r.votes DESC;

    Query: "Best movies from 2020"
    SQL: SELECT DISTINCT t.title_id, t.primary_title, t.genres, r.rating, r.votes 
         FROM titles t 
         JOIN ratings r ON t.title_id = r.title_id 
         WHERE t.type IN ('movie', 'tvMovie')
         AND t.premiered = 2020
         AND r.votes >= 1000 
         ORDER BY r.rating DESC, r.votes DESC;

    PERFORMANCE OPTIMIZATION GUIDELINES:
    - Start queries with the most selective table (usually people for name searches)
    - Use exact name matches when possible (leverages ix_people_name index)
    - Filter by crew.category early (leverages ix_crew_category index)
    - Filter by titles.type early (leverages ix_titles_type index)
    - Put year filters before genre filters (years are more selective)
    - Use INNER JOIN instead of LEFT JOIN when you need the related data
    - Avoid LIKE '%pattern%' when exact matches are possible

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
            max_tokens=1200,
            top_p=0.9
        )
        
        sql_query = response.choices[0].message.content.strip()
        
        # Clean up the SQL query
        sql_query = re.sub(r'^```sql\s*', '', sql_query, flags=re.IGNORECASE)
        sql_query = re.sub(r'^```\s*', '', sql_query)
        sql_query = re.sub(r'\s*```$', '', sql_query)
        sql_query = sql_query.strip()
        
        # Post-process to escape any unescaped single quotes in LIKE patterns
        sql_query = fix_single_quotes_in_sql(sql_query)
        
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

@main.route('/api/generate-summary', methods=['POST'])
def api_generate_summary():
    """API endpoint to generate AI summary for a movie/TV show"""
    logger.info("AI Summary API endpoint called")
    
    try:
        # Log request details
        logger.info(f"Request method: {request.method}")
        logger.info(f"Request content type: {request.content_type}")
        logger.info(f"Request headers: {dict(request.headers)}")
        
        data = request.get_json()
        logger.info(f"Request data received: {data}")
        
        if data is None:
            logger.error("No JSON data received in request")
            return jsonify({
                'success': False,
                'error': 'No JSON data received'
            }), 400
        
        title_id = data.get('title_id', '').strip()
        title_name = data.get('title_name', '').strip()
        
        logger.info(f"Extracted title_id: '{title_id}'")
        logger.info(f"Extracted title_name: '{title_name}'")
        
        if not title_id or not title_name:
            logger.error(f"Missing required fields - title_id: '{title_id}', title_name: '{title_name}'")
            return jsonify({
                'success': False,
                'error': 'Missing title_id or title_name'
            }), 400
        
        logger.info(f"Starting AI summary generation for: {title_name} (ID: {title_id})")
        
        # Get additional title information from database
        logger.info("Fetching title info from database...")
        title_info = get_title_info(title_id)
        logger.info(f"Title info retrieved: {title_info}")
        
        # Generate AI summary
        logger.info("Starting AI summary generation...")
        summary = generate_title_summary(title_name, title_info)
        logger.info(f"AI summary generated successfully. Length: {len(summary)} characters")
        
        response_data = {
            'success': True,
            'summary': summary,
            'title_id': title_id,
            'title_name': title_name
        }
        
        logger.info(f"Returning successful response: {response_data}")
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error generating summary for {title_id}: {str(e)}", exc_info=True)
        error_response = {
            'success': False,
            'error': f'Failed to generate summary: {str(e)}'
        }
        logger.error(f"Returning error response: {error_response}")
        return jsonify(error_response), 500


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
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"Unexpected error during SQL execution: {error_msg}")
        if 'conn' in locals():
            conn.close()
        raise Exception(error_msg)


def get_title_info(title_id):
    """Get additional information about a title from the database"""
    logger.info(f"Fetching title info for title_id: {title_id}")
    
    try:
        logger.info(f"Connecting to database: {DATABASE_PATH}")
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = """
        SELECT t.primary_title, t.type, t.premiered, t.genres, t.runtime_minutes,
               r.rating, r.votes
        FROM titles t 
        LEFT JOIN ratings r ON t.title_id = r.title_id 
        WHERE t.title_id = ?
        """
        
        logger.info(f"Executing query: {query}")
        logger.info(f"Query parameters: {(title_id,)}")
        
        cursor.execute(query, (title_id,))
        result = cursor.fetchone()
        
        logger.info(f"Query result: {dict(result) if result else 'No result found'}")
        
        conn.close()
        
        if result:
            title_info = {
                'title': result['primary_title'],
                'type': result['type'],
                'year': result['premiered'],
                'genres': result['genres'],
                'runtime': result['runtime_minutes'],
                'rating': result['rating'],
                'votes': result['votes']
            }
            logger.info(f"Returning title info: {title_info}")
            return title_info
        
        logger.warning(f"No title found for title_id: {title_id}")
        return {}
        
    except Exception as e:
        logger.error(f"Error fetching title info for {title_id}: {str(e)}", exc_info=True)
        return {}


def generate_title_summary(title_name, title_info):
    """Generate a spoiler-free AI summary of a movie or TV show"""
    logger.info(f"Starting AI summary generation for: {title_name}")
    logger.info(f"Title info provided: {title_info}")
    
    try:
        logger.info("Getting Azure OpenAI client...")
        client = get_azure_client()
        logger.info("Azure client obtained successfully")
        
        # Build context from title information
        context_parts = [f"Title: {title_name}"]
        
        if title_info.get('type'):
            context_parts.append(f"Type: {title_info['type']}")
        if title_info.get('year'):
            context_parts.append(f"Year: {title_info['year']}")
        if title_info.get('genres'):
            context_parts.append(f"Genres: {title_info['genres']}")
        if title_info.get('runtime'):
            context_parts.append(f"Runtime: {title_info['runtime']} minutes")
        if title_info.get('rating'):
            context_parts.append(f"IMDb Rating: {title_info['rating']}/10")
        
        context = " | ".join(context_parts)
        logger.info(f"Built context: {context}")
        
        system_message = """
            You're an expert film and television critic known for engaging, spoiler-free summaries that help audiences decide if a film or show suits their tastes.

            Your task is to craft a compelling, vivid, and informative summary following these detailed guidelines:

            CONTENT GUIDELINES:

            - Provide a spoiler-free description highlighting themes, tone, filmmaking style, general premise, and overall quality.
            - Clearly mention notable cast/crew members (such as directors, actors, writers) if they are widely recognized or celebrated.
            - Include interesting trivia or behind-the-scenes insights, if applicable.
            - Honestly discuss the overall quality: if the movie/show is genuinely poor or disappointing, clearly say so without hesitation—be honest but fair.
            - Highlight what makes this title noteworthy, unique, or memorable within its specific genre or type of storytelling.
            - Keep your writing engaging and concise, vivid yet completely spoiler-free. Avoid clichés, vague statements, or overly generic descriptions.
            - Limit your summary to under 150 words to keep readers engaged.

            FORMATTING INSTRUCTIONS (in clean HTML):

            - Use <p> tags for each main section or paragraph.
            - Italicize title names of movies or shows using the <em> tag.
            - Feel free to use <br> tags for line breaks within paragraphs if needed.
            - Add a "Similar Movies/Shows" section with relevant, thoughtful recommendations, formatted clearly with bullet points or line breaks as appropriate.

            STRICTLY AVOID:

            - Specific plot twists, character deaths, surprises, climaxes, or endings.
            - Vague or overly generic descriptions; be precise, thoughtful, and engaging.
            - Spoiling the viewing experience in any way. Your goal is to intrigue, not reveal.
        """
        
        user_prompt = f"""
        Please write a spoiler-free summary for: {context}
        """
        
        logger.info("Calling Azure OpenAI API...")
        logger.info(f"Model: {AZURE_OPENAI_MODEL}")
        logger.info(f"System message length: {len(system_message)} characters")
        logger.info(f"User prompt length: {len(user_prompt)} characters")
        
        response = client.chat.completions.create(
            model=AZURE_OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,  # Slightly higher for more creative writing
            max_tokens=300,
            top_p=0.9
        )
        
        logger.info("Azure OpenAI API call completed successfully")
        logger.info(f"Response object: {response}")
        
        summary = response.choices[0].message.content.strip()
        logger.info(f"Generated summary for '{title_name}': {len(summary)} characters")
        logger.info(f"Summary content: {summary[:200]}{'...' if len(summary) > 200 else ''}")
        
        return summary
        
    except Exception as e:
        logger.error(f"Error generating summary for '{title_name}': {str(e)}", exc_info=True)
        raise Exception(f"Failed to generate AI summary: {str(e)}")

