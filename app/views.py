from flask import Blueprint, render_template, request
import os
import sqlite3
import logging
from openai import AzureOpenAI
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import AZURE_OPENAI_API_KEY, AZURE_OPENAI_API_VERSION, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_MODEL, DATABASE_PATH

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
    Generate SQL query response using Azure OpenAI GPT-4.1
    """
    client = get_azure_client()
    system_message = """
                As an assistant, your task is to translate natural language queries into SQLite queries against the IMDb database schema consisting of the following tables:
                - people: person_id, name, born, died
                - titles: title_id, type, primary_title, original_title, is_adult, premiered, ended, runtime_minutes, genres
                - akas: title_id, title, region, language, types, attributes, is_original_title                
                - crew: title_id, person_id, category, job, characters
                - episodes: episode_title_id, show_title_id, season_number, episode_number
                - ratings: title_id, rating, votes

                Here are some example natural language inputs translated to SQLite:

                Example 1:
                Input: "Find movies named 'Inception' and their ratings."
                Output: "SELECT t.title_id, t.type, t.primary_title, t.premiered, t.genres, r.rating, r.votes FROM titles t INNER JOIN ratings r ON r.title_id = t.title_id WHERE t.primary_title = 'Inception' AND t.type = 'movie';"

                Example 2:
                Input: "List all episodes of 'The Office' TV show and order them by season and episode number."
                Output: "SELECT e.episode_title_id, e.show_title_id, e.season_number, e.episode_number FROM titles t INNER JOIN episodes e ON t.title_id = e.show_title_id WHERE t.primary_title = 'The Office' AND t.type = 'tvSeries' ORDER BY e.season_number, e.episode_number;"

                Example 3:
                Input: "Find which movies both Leonardo DiCaprio and Tom Hardy acted in together."
                Output: "SELECT DISTINCT t.title_id, t.primary_title, t.premiered, t.genres FROM titles t INNER JOIN crew c1 ON t.title_id = c1.title_id INNER JOIN crew c2 ON t.title_id = c2.title_id WHERE c1.person_id IN (SELECT person_id FROM people WHERE name = 'Leonardo DiCaprio') AND c2.person_id IN (SELECT person_id FROM people WHERE name = 'Tom Hardy') AND c1.category = 'actor' AND c2.category = 'actor' AND t.type = 'movie';"

                Focus on translating the following natural language query into an SQL query. Pick the most relevant columns to show based on the query. Always include rating and votes in the SQL that you generate. 
                
                It's *VERY IMPORTANT* to return ONLY the clean SQL WITHOUT ANY MARKDOWN as the response, that I can DIRECTLY execute on the DB.
                """
    
    response = client.chat.completions.create(
        model=AZURE_OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_query}
        ],
        temperature=0.4,
        max_tokens=600
    )
    
    return response.choices[0].message.content.strip()

@main.route('/', methods=['GET', 'POST'])
def home():
    results = None  # Initialize 'results' to None
    query = ''  # Initialize 'query' to an empty string

    if request.method == 'POST':
        user_query = request.form['query']
        logging.info(f"User query: {user_query}")
        
        # Generate SQL query using GPT-4.1 and execute
        sql_query = generate_response(user_query)
        logging.info(f"SQL query: {sql_query}")
        results, column_names = execute_sql_query(sql_query)
        
        if results:
            logging.info(f"Query returned {len(results)} results")
            results = [dict(zip(column_names, row)) for row in results]  # List of dictionaries for easier template handling
        else:
            logging.info("Query returned no results")

    # Render the same template for both GET and POST, but pass 'results' only if they exist
    return render_template('index.html', results=results, query=user_query if request.method == 'POST' else '')


def execute_sql_query(sql_query, db_path=None):
    """
    Executes the SQL query on the specified database and returns the results along with column names.
    """
    if db_path is None:
        db_path = DATABASE_PATH
        
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute(sql_query)
        results = c.fetchall()
        column_names = [description[0] for description in c.description]
        conn.close()
        return results, column_names
    except sqlite3.Error as e:
        logging.error(f"SQL execution error: {e.args[0]}")  # Log the error
        return [], []

