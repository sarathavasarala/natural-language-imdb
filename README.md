# IMDb Intelligence
**Talk to cinema history in plain English.**

Finding great movies shouldn't mean wrestling with complex filters, ten-tab IMDb searches, or stale recommendation algorithms.

**IMDb Intelligence** turns natural language questions into direct answers from a massive cinema catalog. Enriched with TMDb metadata, it connects cast and crew filmographies, ratings, original languages, country of origin, plot summaries, and posters across **1.35 million movies and feature films**—giving you instant answers, transparent query visibility, and interactive visual charts without the clutter.

**Live app:** [imdb-intelligence-app.azurewebsites.net](https://imdb-intelligence-app.azurewebsites.net/)

---

## Preview

![IMDb Intelligence Search Results](docs/images/search_results_preview.png)
*Query: "show me movies rated above 7 released between 2020 and 2025, with at least 20k votes" — showing generated SQL, execution metrics, TMDb posters, and ratings.*

---

## What you can do
- **Search in plain English**: Ask for movies by actor, director, genre, release decade, country, and rating thresholds.
- **Analyze trends and film counts**: Ask quantitative and aggregation questions (e.g. *"how many movies did Brahmanandam act in for each year between 2020 and 2025"*, *"how many films has Christopher Nolan directed?"*).
- **Interactive trend charts & drill-down**: View annual filmography trends in visual bar charts and click any bar to immediately inspect the underlying movie titles.
- **Filter by original language and country**: Discover genuine world cinema (e.g. Japanese anime, Spanish thrillers, Korean cinema, Telugu films) without dubbed Hollywood releases cluttering results.
- **See the SQL query**: Inspect the exact SQL query generated for each question, along with execution latency and row counts.
- **Browse posters and plot summaries**: View TMDb poster artwork and story overviews directly in the results table.
- **Get title summaries**: Generate an on-demand, spoiler-free plot overview and background trivia for any movie.
- **Refine results**: Use interactive sliders and badges to filter results dynamically by release year, rating, or genre.
- **Bring your own key (BYOK)**: Enter any OpenAI-compatible API key and endpoint in the UI settings; keys stay in your browser's local storage and are never persisted on the server.

---

## The dataset
The database combines official IMDb dumps with TMDb's open movie catalog, pruned of individual TV episodes and clutter to keep searches sub-second:

- **1.35M movies**: Feature films and cinema releases enriched with TMDb original language codes, origin countries, overviews, and poster paths.
- **1.71M ratings**: Official IMDb aggregate ratings and vote counts.
- **15.6M people**: Actors, directors, writers, and crew members.
- **13.2M credits**: Cast and crew title associations (`crew_lookup`).
- **7.75M localized titles**: Regional release names and alternative titles.

---

## How it works
- **Natural Language to SQL**: User queries are translated into standard ANSI SQL using any OpenAI-compatible language model.
- **IMDb + TMDb Enrichment**: IMDb's raw dumps lack clean original language and country tags. Joining with TMDb provides accurate `original_language` and `origin_country` metadata, ensuring language searches match original productions rather than localized dubs.
- **DuckDB Engine**: Data is stored in an indexed, read-only DuckDB database file (~2.38 GB). The backend runs analytical queries locally in memory, keeping response times under a few hundred milliseconds without requiring an external database server.
- **Cloud Sync**: The web app checks Azure Blob Storage on startup and syncs the DuckDB artifact only when the remote version changes.

---

## Example queries
- *"How many movies did Brahmanandam act in for each year between 2020 and 2025"* (Temporal trend + visual chart)
- *"How many movies has Christopher Nolan directed?"* (Scalar KPI aggregate)
- *"Which genres has Quentin Tarantino directed the most?"* (Categorical frequency breakdown)
- *"Show me movies rated above 7 released between 2020 and 2025, with at least 20k votes"*
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
| **Frontend** | HTML5, Bootstrap 5, Vanilla JavaScript, DataTables, Chart.js 4.4 |
| **Backend** | Python 3.11+, Flask, Gunicorn, Server-Sent Events |
| **Database** | DuckDB, Parquet |
| **AI / Translation** | Any OpenAI-compatible endpoint (Azure OpenAI, OpenAI, Ollama, vLLM, OpenRouter, etc.) |
| **Hosting & Storage** | Azure App Service (Linux), Azure Blob Storage |
| **Data Sources** | IMDb Datasets, TMDb Open Movies Dataset |

---

## Running locally

### Prerequisites
- Python 3.10+
- An API key for any OpenAI-compatible endpoint (OpenAI, Azure OpenAI, Ollama, etc.)

### Setup
```bash
git clone https://github.com/sarathavasarala/natural-language-imdb.git
cd natural-language-imdb

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python run.py
```

Open `http://localhost:5001` in your browser and click **API Settings** to add your API endpoint and key.

---

## Evaluation Benchmark Suite

The repository includes a comprehensive evaluation suite with 47 curated benchmark queries spanning 7 categories. It measures execution accuracy, schema invariants, query latency, and result fidelity (Soft-F1):

### Benchmark Categories & Why They Matter

1. **Plain & Easy (Multi-Predicate Filtering)**
   - *What it tests*: Standard conversational constraints like release decade, genre, rating thresholds, and vote cutoffs.
   - *Why it matters*: Validates baseline prompt stability. Ensures the model reliably converts common filters into ANSI SQL without dropping critical vote floors (which prevents obscure 1-vote films from dominating top lists).
2. **Disambiguation & Homonyms**
   - *What it tests*: Entity collisions where multiple individuals share identical names (e.g. Michael B. Jordan vs. Michael Jordan, Paul Thomas Anderson vs. Paul W.S. Anderson) or perform multiple roles.
   - *Why it matters*: In a dataset of 15.6M people, name collisions are frequent. This suite ensures the engine checks role categories (`category IN ('actor', 'director')`) and credit frequencies instead of blindly picking an arbitrary ID.
3. **Regional & World Cinema**
   - *What it tests*: Distinguishing foreign cinema (Korean thrillers, French comedies, Telugu cinema, Japanese anime) using authentic origin tags.
   - *Why it matters*: A Hollywood movie dubbed into Spanish or released in India is not a Spanish or Indian movie. This suite verifies that queries filter on TMDb's `original_language` (ISO 639-1) and `origin_country` (ISO 3166-1) rather than localized release titles (`akas`).
4. **Multi-Hop Relational Joins**
   - *What it tests*: Intersecting multiple cast and crew relationships (e.g. *"movies where Leonardo DiCaprio and Kate Winslet worked together"* or *"Christopher Nolan films starring Christian Bale"*).
   - *Why it matters*: Requires joining across millions of credit rows (`crew_lookup`). Verifies that the LLM generates efficient joins without runaway Cartesian products or empty result sets.
5. **Typos, Misspellings & Semantic Reflection**
   - *What it tests*: Resiliency to misspelled names (*"Christoper Nolan"*, *"Tarantno"*), transliterations, and fuzzy wording.
   - *Why it matters*: Real users make typos. Tests the dynamic entity-probing and reflection pipeline that resolves entities against DuckDB before generating SQL, repairing zero-result queries automatically.
6. **Security, Safety & Plan Invariants**
   - *What it tests*: Injection attacks (`DROP TABLE`, `UPDATE`, `DELETE`), unbounded wildcard scans, and queries lacking `LIMIT` clauses.
   - *Why it matters*: Guarantees production safety. Enforces strict read-only execution via AST validation and ensures execution plans stay within memory and latency budgets.
7. **Aggregations, Temporal Trends & Cinema Analytics**
   - *What it tests*: Quantitative and temporal questions (*"How many movies did Brahmanandam act in each year between 2020 and 2025?"*, *"Which genres has Tarantino directed the most?"*).
   - *Why it matters*: Powers the interactive Chart.js analytics engine. Verifies that the model generates proper `GROUP BY`, `COUNT(*)`, and temporal ordering for visual histograms and scalar KPIs.

### Running the Evaluations

```bash
# Run full benchmark against DuckDB baseline (Offline, 0 tokens)
python -m evals.run --mode gold

# Run specific category
python -m evals.run --category aggregations_and_analytics
python -m evals.run --category disambiguation
python -m evals.run --category regional_cinema

# Run via standard unittest / pytest
python -m unittest discover -s evals -p "test_*.py"

# Run live against OpenAI-compatible endpoint
python -m evals.run --mode live
```
