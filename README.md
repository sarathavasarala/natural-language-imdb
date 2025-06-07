# IMDb Intelligence | AI-Powered Movie Database Search

A professional Flask web application that transforms natural language queries into intelligent IMDb database searches using Azure OpenAI GPT-4.1.

## 🚀 Enhanced Features

### Core Features
- **🧠 Advanced AI Query Processing** - Sophisticated natural language to SQL conversion
- **🎨 Professional UI/UX** - Modern, responsive design with Bootstrap 5
- **⚡ Smart Query Suggestions** - Contextual examples organized by category
- **📊 Real-time Analytics** - Query performance metrics and database statistics
- **🔍 Enhanced Search Results** - Interactive tables with advanced filtering and sorting
- **📱 Responsive Design** - Optimized for desktop, tablet, and mobile
- **🛡️ Security First** - SQL injection protection and query validation

### Advanced Capabilities
- **Fuzzy Name Matching** - Handles typos and partial names intelligently
- **Complex Relationship Queries** - Multi-actor collaborations, director analysis
- **Genre & Era Filtering** - Sophisticated filtering by genre, decade, ratings
- **Performance Optimization** - Efficient database queries with proper indexing
- **Query History** - Local storage of previous searches
- **Copy-to-Clipboard** - Easy sharing of generated SQL queries

### Technical Excellence
- **Comprehensive Logging** - Detailed application and query logging
- **Error Handling** - Graceful error recovery with user-friendly messages
- **API Endpoints** - RESTful APIs for validation and statistics
- **Code Quality** - Professional code structure with proper separation of concerns

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

The IMDB database (`db/imdb.db`) has been created using the `imdb-sqlite` package, which downloads and imports the latest IMDB data from their official TSV files. The database contains:

- **9+ million people** (actors, directors, writers, etc.)
- **5+ million titles** (movies, TV shows, episodes, etc.)  
- **3+ million alternative titles** (different languages/regions)
- **29+ million crew relationships** (who worked on what)
- **3+ million episode records**
- **850k+ ratings**

The database file is approximately 12GB and is excluded from version control via `.gitignore`.

**Note**: If you need to regenerate the database with fresh IMDB data, you can use:
```bash
# Activate the virtual environment
source imdb_env/bin/activate

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

The application will be available at `http://localhost:5000`

## Usage

1. Enter a natural language query in the search box
2. Click "Search with GPT-4.1"
3. View results in the interactive table below

### Example Queries

**Basic Searches:**
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

## Project Structure

```
imdb_project/
├── app/
│   ├── __init__.py
│   ├── views.py          # Main application logic
│   ├── templates/
│   │   └── index.html    # Web interface
│   └── static/
│       └── style.css     # Custom styles
├── db/
│   └── imdb.db          # SQLite database
├── config.py            # Configuration (API keys)
├── config.template.py   # Configuration template
├── requirements.txt     # Python dependencies
└── run.py              # Application entry point
```

## Database Schema

The application uses the following IMDB database tables:

- **people**: person_id, name, born, died
- **titles**: title_id, type, primary_title, original_title, is_adult, premiered, ended, runtime_minutes, genres
- **akas**: title_id, title, region, language, types, attributes, is_original_title
- **crew**: title_id, person_id, category, job, characters
- **episodes**: episode_title_id, show_title_id, season_number, episode_number
- **ratings**: title_id, rating, votes

## Recent Changes

- **Database Created**: IMDB database has been successfully imported using `imdb-sqlite` package
- **Added to .gitignore**: Database file, downloads cache, and virtual environment excluded from version control
- **Removed Groq/LLaMA 3**: Simplified to use only Azure OpenAI GPT-4.1
- **Externalized Configuration**: Moved API keys to separate `config.py` file
- **Simplified Code**: Removed model selection logic and streamlined functions
- **Updated UI**: Removed model selector dropdown from the interface
- **Added Security**: Created `.gitignore` to protect API keys from version control

## Security Notes

- The `config.py` file contains sensitive API keys and is excluded from version control
- Use the `config.template.py` as a reference for required configuration values
- Never commit actual API keys to version control

## Dependencies

- Flask: Web framework
- openai: Azure OpenAI client library
- sqlite3: Database (included with Python)
