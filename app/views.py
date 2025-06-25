from flask import Blueprint, render_template, request, jsonify
import os
import sqlite3
import logging
import json
import time
import re
from openai import AzureOpenAI
import sys
from datetime import datetime
import uuid
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

DB_SCHEMA_PROMPT = """
DATABASE SCHEMA:
- people: person_id (VARCHAR), name (VARCHAR), born (INTEGER), died (INTEGER)
- titles: title_id (VARCHAR), type (VARCHAR), primary_title (VARCHAR), original_title (VARCHAR), is_adult (INTEGER), premiered (INTEGER), ended (INTEGER), runtime_minutes (INTEGER), genres (VARCHAR)
- akas: title_id (VARCHAR), title (VARCHAR), region (VARCHAR), language (VARCHAR), types (VARCHAR), attributes (VARCHAR), is_original_title (INTEGER)
- crew: title_id (VARCHAR), person_id (VARCHAR), category (VARCHAR), job (VARCHAR), characters (VARCHAR)
- episodes: episode_title_id (VARCHAR), show_title_id (VARCHAR), season_number (INTEGER), episode_number (INTEGER)
- ratings: title_id (VARCHAR), rating (REAL), votes (INTEGER)
"""

def get_azure_client():
    """
    Returns the Azure OpenAI client initialized with necessary credentials.
    """
    return AzureOpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        api_version=AZURE_OPENAI_API_VERSION,
        azure_endpoint=AZURE_OPENAI_ENDPOINT
    )

def get_database_connection():
    """Get a connection to the IMDb database"""
    try:
        # Database is in the db/ folder
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'db', 'imdb.db')
        logger.info(f"Connecting to database at: {db_path}")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # This allows dict-like access to rows
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        raise

def execute_sql_query(sql_query):
    """Execute SQL query and return results with column names"""
    try:
        conn = get_database_connection()
        cursor = conn.cursor()
        
        logger.info(f"Executing SQL: {sql_query[:200]}...")
        cursor.execute(sql_query)
        
        # Get column names
        column_names = [description[0] for description in cursor.description] if cursor.description else []
        
        # Fetch results
        results = cursor.fetchall()
        
        conn.close()
        logger.info(f"Query executed successfully, returned {len(results)} rows")
        
        return results, column_names
        
    except Exception as e:
        logger.error(f"SQL execution error: {str(e)}")
        if 'conn' in locals():
            conn.close()
        raise

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

def validate_sql_query(sql_query):
    """Basic validation of SQL query for security and syntax"""
    try:
        # Basic security checks
        sql_lower = sql_query.lower().strip()
        
        # Check for dangerous SQL operations
        dangerous_patterns = ['drop', 'delete', 'update', 'insert', 'alter', 'create', 'truncate']
        for pattern in dangerous_patterns:
            if pattern in sql_lower:
                logger.warning(f"Potentially dangerous SQL operation detected: {pattern}")
                return False
        
        # Must be a SELECT statement
        if not sql_lower.startswith('select'):
            logger.warning("SQL query must be a SELECT statement")
            return False
        
        # Basic syntax validation - try to parse
        try:
            conn = get_database_connection()
            cursor = conn.cursor()
            cursor.execute(f"EXPLAIN QUERY PLAN {sql_query}")
            conn.close()
            return True
        except Exception as e:
            logger.warning(f"SQL syntax validation failed: {str(e)}")
            return False
            
    except Exception as e:
        logger.error(f"SQL validation error: {str(e)}")
        return False

def generate_response(user_query):
    """
    Generate SQL query response using Azure OpenAI GPT-4.1 with enhanced prompt engineering
    """
    start_time = time.time()
    logger.info(f"Processing query: '{user_query}'")
    
    client = get_azure_client()
    
    # Enhanced system message with comprehensive examples and edge cases
    system_message = f"""
    You are an expert SQL query generator for IMDb database analysis. Your task is to convert natural language queries into precise SQLite queries.

    {DB_SCHEMA_PROMPT}

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

# Function Calling Implementation for MVP

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
        conn = get_database_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT t.title_id, t.primary_title, t.original_title, t.premiered, t.ended, 
               t.runtime_minutes, t.genres, t.type, r.rating, r.votes
        FROM titles t
        LEFT JOIN ratings r ON t.title_id = r.title_id
        WHERE t.title_id = ?
        """
        
        cursor.execute(query, (title_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return dict(result)
        return None
        
    except Exception as e:
        logger.error(f"Error fetching title info: {str(e)}")
        return None

def generate_title_summary(title_name, title_info):
    """Generate AI summary for a movie/TV show"""
    try:
        client = get_azure_client()
        
        # Create context from title info
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
            model=AZURE_OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a knowledgeable film and TV expert who provides engaging summaries."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=300
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        logger.error(f"Error generating title summary: {str(e)}")
        return "Unable to generate summary at this time."

# Function Calling Tools Definition
def get_function_tools():
    """Define the available functions for Azure OpenAI function calling"""
    return [
        {
            "type": "function",
            "function": {
                "name": "search_imdb_database",
                "description": "Search the IMDb database for movies, TV shows, people, or analyze data. Can return results as table data or chart-ready data.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query_type": {
                            "type": "string",
                            "enum": ["movie_search", "person_search", "analysis", "collaboration", "chart_data"],
                            "description": "Type of search or analysis to perform"
                        },
                        "search_terms": {
                            "type": "string", 
                            "description": "The search terms, person names, movie titles, or analysis criteria"
                        },
                        "chart_request": {
                            "type": "boolean",
                            "description": "Whether this is for generating a chart"
                        },
                        "filters": {
                            "type": "object",
                            "properties": {
                                "year_range": {"type": "string", "description": "Year range like '2010-2020'"},
                                "genre": {"type": "string", "description": "Movie genre"},
                                "rating_min": {"type": "number", "description": "Minimum rating"}
                            }
                        }
                    },
                    "required": ["query_type", "search_terms"]
                }
            }
        },
        {
            "type": "function", 
            "function": {
                "name": "generate_chart",
                "description": "Create a chart from data (bar chart, line chart, or pie chart)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chart_type": {
                            "type": "string",
                            "enum": ["bar", "line", "pie"],
                            "description": "Type of chart to create"
                        },
                        "data": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "x": {"type": "string", "description": "X-axis value (e.g., year, category)"},
                                    "y": {"type": "number", "description": "Y-axis value (e.g., count, rating)"},
                                    "year": {"type": "number", "description": "Year value for time-based charts"},
                                    "count": {"type": "number", "description": "Count value"},
                                    "label": {"type": "string", "description": "Label for pie charts"},
                                    "value": {"type": "number", "description": "Value for pie charts"}
                                }
                            },
                            "description": "Array of data objects with x and y values"
                        },
                        "title": {
                            "type": "string",
                            "description": "Chart title"
                        },
                        "x_label": {
                            "type": "string", 
                            "description": "X-axis label"
                        },
                        "y_label": {
                            "type": "string",
                            "description": "Y-axis label"
                        }
                    },
                    "required": ["chart_type", "data", "title"]
                }
            }
        }
    ]

def search_imdb_database(query_type, search_terms, chart_request=False, filters=None):
    """Function that can be called by AI to search the IMDb database"""
    try:
        logger.info(f"Function called: search_imdb_database({query_type}, {search_terms}, chart_request={chart_request})")
        logger.info(f"Filters provided: {filters}")
        
        # Generate appropriate SQL based on the request
        if chart_request or query_type == "chart_data":
            # Generate SQL for chart data - focus on person's career over time
            person_name = search_terms.strip()
            # Clean up various chart-related phrases
            person_name = re.sub(r'\b(chart|graph|plot|over time|by year|movies?|films?)\b', '', person_name, flags=re.IGNORECASE)
            person_name = person_name.strip()
            logger.info(f"Extracted person name for chart: '{person_name}'")
            
            sql_query = f"""
            SELECT t.premiered as year, COUNT(*) as count
            FROM people p 
            JOIN crew c ON p.person_id = c.person_id 
            JOIN titles t ON c.title_id = t.title_id 
            WHERE p.name = '{person_name.replace("'", "''")}'
            AND c.category IN ('actor', 'actress')
            AND t.type IN ('movie', 'tvMovie')
            AND t.premiered IS NOT NULL
            GROUP BY t.premiered
            ORDER BY t.premiered
            """
            logger.info(f"Generated chart SQL query: {sql_query}")
        else:
            # Use existing SQL generation for regular queries
            logger.info("Using regular SQL generation")
            sql_query = generate_response(search_terms)
        
        # Validate the generated SQL query before execution
        if not validate_sql_query(sql_query):
            logger.error(f"Generated SQL query failed validation: {sql_query}")
            return {
                "success": False,
                "error": "Generated SQL query is invalid or disallowed.",
                "sql_query": sql_query,
                "results": [],
                "column_names": [],
                "row_count": 0
            }

        # Execute the query
        logger.info("Executing SQL query...")
        results, column_names = execute_sql_query(sql_query)
        
        # Convert to dictionaries
        results_dict = [dict(zip(column_names, row)) for row in results]
        logger.info(f"Query executed successfully. Results: {len(results_dict)} rows")
        
        # Log first few results for debugging
        if results_dict:
            logger.info(f"Sample result: {results_dict[0]}")
        
        return {
            "success": True,
            "results": results_dict,
            "sql_query": sql_query,
            "column_names": column_names,
            "row_count": len(results_dict)
        }
        
    except Exception as e:
        logger.error(f"Error in search_imdb_database: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "results": [],
            "sql_query": "",
            "column_names": [],
            "row_count": 0
        }

def generate_chart_function(chart_type, data, title, x_label="", y_label=""):
    """Function that can be called by AI to generate chart data"""
    try:
        logger.info(f"Function called: generate_chart({chart_type}, {title})")
        logger.info(f"Data received: {len(data) if data else 0} items")
        logger.info(f"Labels: x_label='{x_label}', y_label='{y_label}'")
        
        if not data:
            logger.warning("No data provided for chart generation")
            return {
                "success": False,
                "error": "No data provided for chart"
            }
        
        # Log sample data for debugging
        if data:
            logger.info(f"Sample data item: {data[0]}")
        
        # Convert data to Chart.js format
        if chart_type == "bar":
            logger.info("Creating bar chart")
            chart_data = {
                "type": "bar",
                "data": {
                    "labels": [str(item.get('year', item.get('x', ''))) for item in data],
                    "datasets": [{
                        "label": y_label or "Count",
                        "data": [item.get('count', item.get('y', 0)) for item in data],
                        "backgroundColor": "rgba(54, 162, 235, 0.6)",
                        "borderColor": "rgba(54, 162, 235, 1)",
                        "borderWidth": 1
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": title
                        }
                    },
                    "scales": {
                        "x": {
                            "title": {
                                "display": True,
                                "text": x_label or "Year"
                            }
                        },
                        "y": {
                            "title": {
                                "display": True,
                                "text": y_label or "Count"
                            }
                        }
                    }
                }
            }
        elif chart_type == "pie":
            logger.info("Creating pie chart")
            chart_data = {
                "type": "pie",
                "data": {
                    "labels": [str(item.get('label', item.get('x', ''))) for item in data],
                    "datasets": [{
                        "data": [item.get('value', item.get('y', 0)) for item in data],
                        "backgroundColor": [
                            "rgba(255, 99, 132, 0.6)",
                            "rgba(54, 162, 235, 0.6)",
                            "rgba(255, 205, 86, 0.6)",
                            "rgba(75, 192, 192, 0.6)",
                            "rgba(153, 102, 255, 0.6)"
                        ]
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "title": {
                            "display": True,
                            "text": title
                        }
                    }
                }
            }
        else:
            logger.error(f"Unsupported chart type: {chart_type}")
            return {
                "success": False,
                "error": f"Unsupported chart type: {chart_type}"
            }
        
        logger.info("Chart data generated successfully")
        
        return {
            "success": True,
            "chart_data": chart_data,
            "chart_id": str(uuid.uuid4())
        }
        
    except Exception as e:
        logger.error(f"Error in generate_chart: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }

# New Chat API endpoint with function calling
@main.route('/api/chat', methods=['POST'])
def api_chat():
    """Main conversational endpoint with function calling support"""
    request_id = str(uuid.uuid4())[:8]  # Short request ID for tracking
    
    try:
        logger.info(f"[{request_id}] ===== CHAT API REQUEST STARTED =====")
        logger.info(f"[{request_id}] Request method: {request.method}")
        logger.info(f"[{request_id}] Request URL: {request.url}")
        logger.info(f"[{request_id}] Request headers: {dict(request.headers)}")
        logger.info(f"[{request_id}] Client IP: {request.remote_addr}")
        
        data = request.get_json()
        logger.info(f"[{request_id}] Request data: {data}")
        
        user_query = data.get('query', '').strip() if data else ''
        logger.info(f"[{request_id}] Extracted user query: '{user_query}'")
        logger.info(f"[{request_id}] Query length: {len(user_query)}")
        
        if not user_query:
            logger.warning(f"[{request_id}] Empty query received")
            return jsonify({
                "success": False,
                "error": "Query cannot be empty",
                "request_id": request_id
            }), 400
        
        logger.info(f"[{request_id}] Chat API called with query: {user_query}")
        
        # Initialize conversation
        conversation_id = str(uuid.uuid4())
        logger.info(f"[{request_id}] Generated conversation ID: {conversation_id}")
        
        # Create client and define tools
        logger.info(f"[{request_id}] Creating Azure OpenAI client...")
        client = get_azure_client()
        logger.info(f"[{request_id}] Azure OpenAI client created successfully")
        
        tools = get_function_tools()
        logger.info(f"[{request_id}] Function tools defined: {len(tools)} tools")
        for i, tool in enumerate(tools):
            logger.info(f"[{request_id}] Tool {i+1}: {tool['function']['name']}")
        
        # System message for conversational AI with function calling
        system_message = """You are a helpful IMDb database assistant. You can search for movies, TV shows, people, and create charts from the data.

When users ask questions:
1. Respond naturally and conversationally
2. Use the available functions to search the database or create charts
3. Provide insights and summaries of the results
4. If creating charts, explain what the chart shows

Available functions:
- search_imdb_database: Search for movies, people, analyze data
- generate_chart: Create bar charts, line charts, or pie charts

CRITICAL INSTRUCTIONS FOR CHART REQUESTS:
When a user asks to "plot", "chart", "graph", "draw", "visualize", or "show a chart" of data:
1. ALWAYS call search_imdb_database with chart_request=True to get the data
2. IMMEDIATELY after, call generate_chart to create the visualization
3. Both function calls are MANDATORY for chart requests - do not skip the generate_chart step

Example: For "plot Tom Cruise movies by year":
1. Call search_imdb_database(query_type="person_search", search_terms="Tom Cruise", chart_request=True)
2. Call generate_chart(chart_type="bar", data=<results>, title="Tom Cruise Movies by Year", x_label="Year", y_label="Movies")

The user expects to see both the data AND the chart visualization."""

        # First API call with function calling
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_query}
        ]
        
        logger.info(f"[{request_id}] Sending request to Azure OpenAI with model: {AZURE_OPENAI_MODEL}")
        logger.info(f"[{request_id}] Message count: {len(messages)}")
        logger.info(f"[{request_id}] Tools count: {len(tools)}")
        logger.info(f"[{request_id}] System message length: {len(system_message)} characters")
        
        response = client.chat.completions.create(
            model=AZURE_OPENAI_MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.7,
            max_tokens=1500
        )
        
        logger.info(f"[{request_id}] ✅ Received response from Azure OpenAI")
        
        response_message = response.choices[0].message
        ai_response = response_message.content or ""
        
        logger.info(f"[{request_id}] AI response content length: {len(ai_response) if ai_response else 0}")
        logger.info(f"[{request_id}] Tool calls detected: {len(response_message.tool_calls) if response_message.tool_calls else 0}")
        
        # Track function calls and results
        function_calls = []
        chart_data = None
        search_results = None
        
        # Handle function calls if any
        if response_message.tool_calls:
            logger.info(f"[{request_id}] Processing {len(response_message.tool_calls)} tool calls")
            messages.append(response_message)
            
            for i, tool_call in enumerate(response_message.tool_calls):
                function_name = tool_call.function.name
                logger.info(f"[{request_id}] Processing tool call {i+1}/{len(response_message.tool_calls)}: {function_name}")
                
                try:
                    function_args = json.loads(tool_call.function.arguments)
                    logger.info(f"[{request_id}] Tool call {i+1} arguments: {function_args}")
                except json.JSONDecodeError as e:
                    logger.error(f"[{request_id}] Failed to parse function arguments: {tool_call.function.arguments}")
                    logger.error(f"[{request_id}] JSON decode error: {str(e)}")
                    continue
                
                function_calls.append({
                    "function": function_name,
                    "arguments": function_args,
                    "status": "executing"
                })
                
                # Execute the function
                try:
                    if function_name == "search_imdb_database":
                        logger.info(f"[{request_id}] Executing search_imdb_database with: {function_args}")
                        function_result = search_imdb_database(**function_args)
                        search_results = function_result
                        logger.info(f"[{request_id}] Search completed. Success: {function_result.get('success')}, Results: {function_result.get('row_count', 0)}")
                        
                        # Auto-generate chart if this was a chart request and we have chart-ready data
                        if (function_args.get('chart_request') or function_args.get('query_type') == 'chart_data') and function_result.get('success'):
                            chart_data_results = function_result.get('results', [])
                            if chart_data_results and len(chart_data_results) > 0:
                                logger.info(f"[{request_id}] Auto-generating chart from {len(chart_data_results)} search results")
                                
                                # Check if the data already has year/count columns (pre-aggregated)
                                first_result = chart_data_results[0]
                                if 'year' in first_result and 'count' in first_result:
                                    # Data is already aggregated
                                    chart_title = f"{function_args.get('search_terms')} Movies Over Time"
                                    chart_result = generate_chart_function(
                                        chart_type="bar",
                                        data=chart_data_results,
                                        title=chart_title,
                                        x_label="Year",
                                        y_label="Number of Movies"
                                    )
                                    chart_data = chart_result
                                    logger.info(f"[{request_id}] Auto-chart generation completed (pre-aggregated). Success: {chart_result.get('success')}")
                                
                                # Check if we have raw movie data with years that we can aggregate
                                elif 'premiered' in first_result or 'year' in first_result:
                                    logger.info(f"[{request_id}] Found raw movie data with years, aggregating for chart")
                                    
                                    # Group by year and count
                                    year_counts = {}
                                    for result in chart_data_results:
                                        year = result.get('premiered') or result.get('year')
                                        if year and year != 'None' and year != '\\N':
                                            try:
                                                year = int(year)  # Ensure it's an integer
                                                year_counts[year] = year_counts.get(year, 0) + 1
                                            except (ValueError, TypeError):
                                                continue
                                    
                                    if year_counts:
                                        # Convert to chart data format
                                        chart_data_list = [
                                            {"x": str(year), "y": count, "year": year, "count": count}
                                            for year, count in sorted(year_counts.items())
                                        ]
                                        
                                        # Extract person/search terms for chart title
                                        search_terms = function_args.get('search_terms', 'Movies')
                                        chart_title = f"{search_terms} by Year"
                                        
                                        logger.info(f"[{request_id}] Creating chart with {len(chart_data_list)} data points")
                                        chart_result = generate_chart_function(
                                            chart_type="bar",
                                            data=chart_data_list,
                                            title=chart_title,
                                            x_label="Year",
                                            y_label="Number of Movies"
                                        )
                                        chart_data = chart_result
                                        logger.info(f"[{request_id}] Auto-chart generation completed (aggregated). Success: {chart_result.get('success')}")
                                        
                                        # Add this as a function call for tracking
                                        function_calls.append({
                                            "function": "generate_chart",
                                            "arguments": {
                                                "chart_type": "bar",
                                                "data": chart_data_list,
                                                "title": chart_title,
                                                "x_label": "Year", 
                                                "y_label": "Number of Movies"
                                            },
                                            "status": "completed",
                                            "result": chart_result
                                        })
                                    else:
                                        logger.warning(f"[{request_id}] No valid year data found for chart generation")
                        
                    elif function_name == "generate_chart":
                        logger.info(f"[{request_id}] Executing generate_chart with: {function_args}")
                        function_result = generate_chart_function(**function_args)
                        chart_data = function_result
                        logger.info(f"[{request_id}] Chart generation completed. Success: {function_result.get('success')}")
                    else:
                        logger.error(f"[{request_id}] Unknown function called: {function_name}")
                        function_result = {"error": f"Unknown function: {function_name}"}
                except Exception as func_error:
                    logger.error(f"[{request_id}] Error executing function {function_name}: {str(func_error)}", exc_info=True)
                    function_result = {"error": str(func_error), "success": False}
                
                # Add function result to conversation
                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool", 
                    "name": function_name,
                    "content": json.dumps(function_result)
                })
                
                # Update function call status
                function_calls[-1]["status"] = "completed"
                function_calls[-1]["result"] = function_result
        
            # Get final response from AI
            logger.info(f"[{request_id}] Getting final response from AI after function execution")
            final_response = client.chat.completions.create(
                model=AZURE_OPENAI_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=800
            )
            
            ai_response = final_response.choices[0].message.content
            logger.info(f"[{request_id}] Final AI response length: {len(ai_response) if ai_response else 0}")
        
        # Prepare response
        response_data = {
            "success": True,
            "conversation_id": conversation_id,
            "ai_response": ai_response,
            "function_calls": function_calls,
            "search_results": search_results,
            "chart_data": chart_data,
            "timestamp": datetime.now().isoformat(),
            "request_id": request_id
        }
        
        logger.info(f"[{request_id}] ✅ Chat API response prepared successfully. Function calls: {len(function_calls)}")
        logger.info(f"[{request_id}] Response data keys: {list(response_data.keys())}")
        logger.info(f"[{request_id}] ===== CHAT API REQUEST COMPLETED =====")
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"[{request_id}] ❌ Error in chat API: {str(e)}", exc_info=True)
        logger.error(f"[{request_id}] Error type: {type(e).__name__}")
        if hasattr(e, 'response'):
            logger.error(f"[{request_id}] HTTP response: {e.response}")
        logger.error(f"[{request_id}] ===== CHAT API REQUEST FAILED =====")
        return jsonify({
            "success": False,
            "error": str(e),
            "ai_response": "I apologize, but I encountered an error processing your request.",
            "request_id": request_id
        }), 500

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
            'message': 'Query seems too short, please provide more details',
            'suggestions': ['Try: "Movies with Tom Hanks"', 'Try: "Highest rated sci-fi movies"']
        })
    
    # Basic validation - no special characters, must contain letters
    if not re.search(r'[a-zA-Z]', query):
        return jsonify({
            'valid': False,
            'message': 'Query must contain at least one letter',
            'suggestions': ['Try: "Movies with Tom Hanks"', 'Try: "Highest rated sci-fi movies"']
        })
    
    return jsonify({
        'valid': True,
        'message': 'Query is valid'
    })

@main.route('/api/execute', methods=['POST'])
def api_execute_query():
    """API endpoint to execute a SQL query directly (for admin use)"""
    data = request.get_json()
    sql_query = data.get('query', '').strip()
    
    if not sql_query:
        return jsonify({
            'status': 'error',
            'message': 'SQL query cannot be empty'
        }), 400
    
    try:
        # For safety, validate SQL query before execution
        if not validate_sql_query(sql_query):
            return jsonify({
                'status': 'error',
                'message': 'Invalid SQL query',
                'query': sql_query
            }), 400
        
        results, column_names = execute_sql_query(sql_query)
        
        # Convert results to list of dictionaries
        results = [dict(zip(column_names, row)) for row in results]
        
        return jsonify({
            'status': 'success',
            'results': results
        }), 200
    
    except Exception as e:
        logger.error(f"Error executing SQL query: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@main.route('/api/title_info', methods=['POST'])
def api_title_info():
    """API endpoint to get detailed title information"""
    data = request.get_json()
    title_id = data.get('title_id', '').strip()
    
    if not title_id:
        return jsonify({
            'status': 'error',
            'message': 'Title ID is required'
        }), 400
    
    try:
        title_info = get_title_info(title_id)
        
        if not title_info:
            return jsonify({
                'status': 'error',
                'message': 'Title not found'
            }), 404
        
        return jsonify({
            'status': 'success',
            'title_info': title_info
        }), 200
    
    except Exception as e:
        logger.error(f"Error fetching title info: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@main.route('/api/generate_summary', methods=['POST'])
def api_generate_summary():
    """API endpoint to generate AI summary for a title"""
    data = request.get_json()
    title_name = data.get('title_name', '').strip()
    title_id = data.get('title_id', '').strip()
    
    if not title_name or not title_id:
        return jsonify({
            'status': 'error',
            'message': 'Title name and ID are required'
        }), 400
    
    try:
        # For safety, validate title ID format (simple check)
        if not re.match(r'^[\w-]+$', title_id):
            return jsonify({
                'status': 'error',
                'message': 'Invalid Title ID format'
            }), 400
        
        # Fetch title info from database
        title_info = get_title_info(title_id)
        
        if not title_info:
            return jsonify({
                'status': 'error',
                'message': 'Title not found'
            }), 404
        
        # Generate summary using AI
        summary = generate_title_summary(title_name, title_info)
        
        return jsonify({
            'status': 'success',
            'summary': summary
        }), 200
    
    except Exception as e:
        logger.error(f"Error generating summary: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

