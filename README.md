# IMDb Intelligence
Natural language search across IMDb, enriched with TMDb.

IMDb Intelligence translates plain English questions into SQL and runs them against a local DuckDB database. It combines IMDb's cast, crew, and rating histories with TMDb's open metadata to give you original languages, countries of origin, plot summaries, and posters across 1.35 million movies and TV series.

**Live app:** [imdb-intelligence-app.azurewebsites.net](https://imdb-intelligence-app.azurewebsites.net/)

---

## What you can do
- **Search in plain English**: Ask for titles by actor, director, genre, release decade, country, and rating thresholds.
- **Filter by original language and country**: Search for genuine regional cinema (e.g. Japanese anime, Spanish thrillers, Telugu films) without dubbed Hollywood releases cluttering results.
- **See the SQL query**: Inspect the exact SQL query generated for each question, along with execution times and row counts.
- **Browse posters and plot summaries**: View TMDb poster artwork and story overviews directly in the results table.
- **Get title summaries**: Generate a quick spoiler-free plot overview and background trivia for any title.
- **Refine results**: Use interactive sliders and badges to narrow down results by release year, rating, or genre.
- **Bring your own key**: Enter your Azure OpenAI or OpenAI API key in the UI settings; keys stay in your browser's local storage and are never saved on the server.

---

## The dataset
The database combines official IMDb dumps with TMDb's open movie catalog, pruned of individual TV episode entries to keep searches fast:

- **1.35M titles**: Feature films, TV series, mini-series, and TV movies with TMDb language codes, origin countries, and plot summaries.
- **1.71M ratings**: Official IMDb aggregate ratings and vote counts.
- **15.6M people**: Actors, directors, writers, and crew members.
- **13.2M credits**: Cast and crew title associations (`crew_lookup`).
- **7.75M localized titles**: Regional release names and alternative titles.

---

## How it works
- **Natural Language to SQL**: User queries are translated into standard ANSI SQL using Azure OpenAI or OpenAI models.
- **IMDb + TMDb Enrichment**: IMDb's raw dumps lack clean original language and country tags. Joining with TMDb provides accurate `original_language` and `origin_country` metadata, ensuring language searches match original productions rather than localized dubs.
- **DuckDB Engine**: Data is stored in an indexed, read-only DuckDB database file (~2.38 GB). The backend runs analytical queries locally in memory, keeping response times under a few hundred milliseconds without requiring an external database server.
- **Cloud Sync**: The web app checks Azure Blob Storage on startup and syncs the DuckDB artifact only when the remote version changes.

---

## Example queries
- *"Highest rated sci-fi movies from 2010s with over 100k votes"*
- *"Movies where Leonardo DiCaprio and Kate Winslet worked together"*
- *"Best Korean thriller movies released after 2015"*
- *"Top rated animated movies directed by Hayao Miyazaki"*
- *"Highest rated movies from India released after 2000 with at least 30k votes"*
- *"Spanish horror movies with rating above 7.5"*

---

## Tech Stack

| Layer | Stack |
| :--- | :--- |
| **Frontend** | HTML5, Bootstrap 5, Vanilla JavaScript, DataTables |
| **Backend** | Python 3.11+, Flask, Gunicorn, Server-Sent Events |
| **Database** | DuckDB, Parquet |
| **AI / Translation** | Azure OpenAI / OpenAI API (`gpt-4o`, `gpt-5.4`) |
| **Hosting & Storage** | Azure App Service (Linux), Azure Blob Storage |
| **Data Sources** | IMDb Datasets, TMDb Open Movies Dataset |

---

## Running locally

### Prerequisites
- Python 3.10+
- Azure OpenAI or OpenAI API key

### Setup
```bash
git clone https://github.com/sarathavasarala/natural-language-imdb.git
cd natural-language-imdb

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python run.py
```

Open `http://localhost:5001` in your browser and click **API Settings** to add your API credentials.

---

## Evaluation Suite

The repository includes an evaluation benchmark suite covering 6 categories: Plain & Easy, Disambiguation & Homonyms, Regional & Local Cinema, Multi-Hop Relational Joins, Typos & Reflection, and Security & Plan Invariants.

```bash
# Run full benchmark against DuckDB baseline (Offline, 0 tokens)
python -m evals.run --mode gold

# Run specific category
python -m evals.run --category disambiguation
python -m evals.run --category regional_cinema

# Run via standard unittest / pytest
python -m unittest discover -s evals -p "test_*.py"

# Run live against Azure OpenAI
python -m evals.run --mode live
```

