# IMDb Text-to-SQL Search

A Flask web application that converts natural language queries into SQL searches against an IMDb database using Azure OpenAI.

## Features

- Natural language to SQL conversion using models hosted on Azure OpenAI
- Web interface for query input and results display
- Query suggestions and examples
- Interactive data tables for viewing results
- Copy generated SQL queries for further analysis
- AI-powered chat interface for conversational search and data exploration
- Dynamic chart generation for visualizing data (e.g., movies per year for an actor)
- AI-generated summaries for individual movie/TV show titles

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API Keys

1. Copy the configuration template:
   ```bash
   cp config.template.py config.py
   ```

2. Edit `config.py` and add your Azure OpenAI credentials:
   ```python
   AZURE_OPENAI_API_KEY = "your_api_key_here"
   AZURE_OPENAI_ENDPOINT = "https://your-resource.openai.azure.com/"
   ```

### 3. Database Setup

The IMDb database (`db/imdb.db`) is created using the `imdb-sqlite` package, which downloads and imports the latest IMDb data from their official TSV files. The database contains:

- 9+ million people (actors, directors, writers, etc.)
- 5+ million titles (movies, TV shows, episodes, etc.)  
- 3+ million alternative titles (different languages/regions)
- 29+ million crew relationships (who worked on what)
- 3+ million episode records
- 850k+ ratings

The database file is approximately 19GB and is excluded from version control.

**Note**: To regenerate the database with fresh IMDb data:
```bash
# Remove old database and cache (optional)
rm -f db/imdb.db
rm -rf downloads/

# Import fresh data
imdb-sqlite --db db/imdb.db --cache-dir downloads --verbose
```

### 4. Run the Application

```bash
python run.py
```

The application will be available at `http://localhost:5001`

## Usage

The application offers two main modes of interaction:

**1. Simple Search (Default Tab):**
   1. Enter a natural language query in the search box (e.g., "Highest rated movies from 2023").
   2. Click "Search with AI" to process your query.
   3. View results in the interactive table that appears below the search box.
   4. Use the sidebar suggestions for query examples.
   5. You can copy the generated SQL query for further analysis.
   6. Click on the "AI Summary" button next to a title in the results to get an AI-generated summary for that movie or show.

**2. AI Chat (Navigate to "AI Chat" Tab):**
   1. Use the chat interface to ask questions or give instructions conversationally (e.g., "Can you find sci-fi movies starring Keanu Reeves?").
   2. The AI will respond, potentially asking clarifying questions or providing results directly in the chat.
   3. For queries that can be visualized, you can ask for charts (e.g., "Plot Harrison Ford's movies by year"). The AI will generate and display the chart in the chat.
   4. Search results from the chat may also be displayed in a compact table within the chat interface.

### Example Queries

**Basic Searches (Can be used in Simple Search or AI Chat):**
- "Find movies where Robert De Niro and Al Pacino acted together"
- "Show me the highest rated movies from 2020"
- "List all episodes of The Office TV show"
- "What are Christopher Nolan's top rated movies?"

**Advanced Searches:**
- "Sci-fi movies from the 2010s with ratings above 8.0 starring actors who were also in Marvel movies"
- "Directors who made both horror and comedy movies with their highest-rated film in each genre"
- "TV shows that ran for exactly 5 seasons and had more than 100 episodes"
- "Most popular movie genres by decade since 1990"
- "Actors who appeared in both Oscar Best Picture winners and movies rated below 5.0"

**Complex Analysis:**
- "Find actors who worked with the same director more than 3 times"
- "Movies with the biggest rating difference between critics and audience"
- "Child actors who became successful adult actors with their career progression"

**Chart Generation (Primarily for AI Chat):**
- "Plot Tom Hanks movies by year"
- "Show a chart of Christopher Nolan's film ratings over time"
- "Visualize the number of movies released each year in the 1990s"
- "Draw a graph of movie counts for Harrison Ford by decade"

## Project Structure

```
imdb_project/
├── app/
│   ├── __init__.py
│   ├── views.py          # Main application logic and API endpoints
│   ├── templates/
│   │   └── index.html    # Web interface
│   └── static/
│       ├── style.css     # Styles
│       └── app.js        # Frontend functionality
├── db/
│   └── imdb.db          # SQLite database (12GB, excluded from git)
├── config.py            # Configuration (API keys, excluded from git)
├── config.template.py   # Configuration template
├── requirements.txt     # Python dependencies
├── run.py              # Application entry point
└── README.md           # This file
```

## Database Schema

The application uses the following IMDb database tables:

- **people**: person_id, name, born, died
- **titles**: title_id, type, primary_title, original_title, is_adult, premiered, ended, runtime_minutes, genres
- **akas**: title_id, title, region, language, types, attributes, is_original_title
- **crew**: title_id, person_id, category, job, characters
- **episodes**: episode_title_id, show_title_id, season_number, episode_number
- **ratings**: title_id, rating, votes

## Configuration

The `config.py` file contains API keys and is excluded from version control. Use `config.template.py` as a reference for required configuration values.

## Dependencies

- Flask: Web framework
- openai: Azure OpenAI client library
- sqlite3: Database (included with Python)
