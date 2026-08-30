# AGENTS.md — Developer & AI Agent Guidelines

This document provides system design, architectural references, and workflows for developers and AI agents working on the **IMDb Intelligence (Natural Language Text-to-SQL)** project.

---

## 1. Project Overview

`imdb_project` is an intelligent conversational search engine and analytical dashboard for the entire IMDb dataset. It allows users to search movies, TV series, actors, directors, and ratings using natural conversational language.

### Core Capabilities:
- **Natural Language Text-to-SQL**: Converts complex queries into standard ANSI SQL using Azure AI Foundry / Azure OpenAI models (e.g. `gpt-4o`, `gpt-5.4`).
- **Cloud-Native DuckDB Query Engine**: Executes queries directly against remote ZSTD-compressed Parquet datasets stored in **Azure Blob Storage** via HTTP Range Requests (Zero local disk requirement, ~1.3 GB cloud storage).
- **Interactive AI Chat & Visualizations**: Interactive conversational interface capable of generating dynamic Chart.js visualizations (timelines, bar charts) and instant title summaries.
- **Client-Side Key Management (LocalStorage)**: Secure BYOK (Bring Your Own Key) model where users configure their Azure OpenAI keys via the UI settings modal. Keys are persisted in browser `localStorage` and sent over HTTPS request headers without needing hardcoded server secrets.

---

## 2. Architecture & Tech Stack

```
                               ┌────────────────────────────────────────┐
                               │             Browser Client             │
                               │  - HTML5 / Bootstrap 5 / DataTables    │
                               │  - LocalStorage (API Key / Endpoint)   │
                               │  - Chart.js Visualizations             │
                               └───────────────────┬────────────────────┘
                                                   │ HTTPS + Headers
                                                   ▼
┌───────────────────────────────────────────────────────────────────────┐
│                      Flask Backend (Gunicorn)                         │
│                                                                       │
│  app/views.py                                                         │
│  ├── Dynamic Azure Credential Extractor (X-Azure-API-Key / Header)    │
│  ├── AzureOpenAI Client (Tool calling & Text-to-SQL generation)       │
│  └── In-Memory DuckDB Engine (Loaded with 'azure' & 'httpfs' ext)     │
└───────────────┬───────────────────────────────────────┬───────────────┘
                │                                       │
       HTTP Range Requests                     API Completions
                │                                       │
                ▼                                       ▼
┌───────────────────────────────┐       ┌───────────────────────────────┐
│       Azure Blob Storage      │       │       Azure AI Foundry        │
│   (Account: stimdbdataeastus) │       │   (Azure OpenAI Deployments)  │
│   Container: imdb-data        │       │   - gpt-4o / gpt-5.4          │
│   - titles.parquet   (276 MB) │       └───────────────────────────────┘
│   - ratings.parquet  (8.5 MB) │
│   - people.parquet   (147 MB) │
│   - crew.parquet     (544 MB) │
│   - episodes.parquet (50 MB)  │
│   - akas.parquet     (315 MB) │
└───────────────────────────────┘
```

---

## 3. Directory Layout

```
imdb_project/
├── app/
│   ├── __init__.py          # Flask application factory
│   ├── views.py             # Route handlers, DuckDB query execution, LLM prompts
│   ├── templates/
│   │   ├── index.html       # Simple Search page + Settings Modal
│   │   └── chat.html        # AI Chat & Visualization page + Settings Modal
│   └── static/
│       ├── style.css        # Custom UI styling, gradients, and badges
│       ├── app.js           # AJAX handlers, DataTables, LocalStorage manager, Chart.js
│       └── favicon.png      # Application favicon
├── scripts/
│   └── etl_imdb_to_parquet.py # Automated ETL pipeline (IMDb TSVs -> Azure Blob Parquet)
├── Dockerfile               # Production container definition (Python 3.11-slim + DuckDB)
├── docker-compose.yml       # Local container orchestration
├── requirements.txt         # Python dependencies
├── run.py                   # Application entry point (port 5001)
├── config.template.py       # Configuration template
├── config.py                # Local config / environment fallback (gitignored)
├── AGENTS.md                # This agent specification
└── README.md                # User & deployment guide
```

---

## 4. Database Schema (Parquet / DuckDB Views)

The following views are mapped automatically to `azure://imdb-data/*.parquet`:

1. **`titles`**:
   - `title_id` (TEXT, e.g. `'tt0111161'`)
   - `type` (TEXT: `'movie'`, `'tvSeries'`, `'short'`, `'tvEpisode'`, etc.)
   - `primary_title` (TEXT)
   - `original_title` (TEXT)
   - `is_adult` (INTEGER: 0 or 1)
   - `premiered` (INTEGER: release year)
   - `ended` (INTEGER: end year for series)
   - `runtime_minutes` (INTEGER)
   - `genres` (TEXT: comma-separated, e.g. `'Drama,Crime'`)

2. **`ratings`**:
   - `title_id` (TEXT)
   - `rating` (FLOAT: 1.0 to 10.0)
   - `votes` (INTEGER)

3. **`people`**:
   - `person_id` (TEXT, e.g. `'nm0000151'`)
   - `name` (TEXT)
   - `born` (INTEGER: birth year)
   - `died` (INTEGER: death year or NULL)

4. **`crew`**:
   - `title_id` (TEXT)
   - `person_id` (TEXT)
   - `category` (TEXT: `'actor'`, `'actress'`, `'director'`, `'writer'`, `'producer'`, etc.)
   - `job` (TEXT)
   - `characters` (TEXT: JSON or character string)

5. **`episodes`**:
   - `episode_title_id` (TEXT)
   - `show_title_id` (TEXT)
   - `season_number` (INTEGER)
   - `episode_number` (INTEGER)

6. **`akas`**:
   - `title_id` (TEXT)
   - `title` (TEXT)
   - `region` (TEXT: e.g. `'US'`, `'GB'`, `'FR'`)
   - `language` (TEXT)
   - `types` (TEXT)
   - `attributes` (TEXT)
   - `is_original_title` (INTEGER: 0 or 1)

---

## 5. Key Conventions & Best Practices

1. **Never Commit Secrets**:
   - All Azure OpenAI keys and storage connection strings must stay in `config.py` (which is gitignored) or browser LocalStorage.
2. **DuckDB Secret Initialization**:
   - DuckDB views are created on `_duckdb_con` using `CREATE SECRET (TYPE AZURE, CONNECTION_STRING '...')`.
   - Always load both `azure` and `httpfs` extensions before querying `azure://` URIs.
3. **ETL Pipeline**:
   - Run `python scripts/etl_imdb_to_parquet.py` to refresh Parquet files directly from IMDb's official gzip dumps into Azure Blob Storage.
4. **Isolated Resource Group**:
   - Deployments must be kept inside the dedicated resource group `rg-imdb-intelligence`.
