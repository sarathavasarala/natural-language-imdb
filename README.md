# IMDb Intelligence — Natural Language Text-to-SQL Search

A modern web application that converts natural language questions into SQL queries against the complete IMDb dataset using **Azure AI Foundry / OpenAI** and executes them with **DuckDB** directly over **Azure Blob Storage** Parquet files.

![IMDb Intelligence Interface](natural%20language%20imdb.jpeg)

🌐 **Live Demo:** [https://imdb-intelligence-app.azurewebsites.net](https://imdb-intelligence-app.azurewebsites.net)

---

## 🌟 Key Features

- **Natural Language to SQL**: Converts questions into optimized ANSI SQL queries via Azure OpenAI (`gpt-4o`, `gpt-5.4`).
- **Serverless Parquet Engine (DuckDB)**: Queries compressed Parquet files directly on Azure Blob Storage over HTTP Range Requests with **zero local disk footprint** (~1.3 GB cloud total vs. 19 GB SQLite).
- **Client-Side Key Management (LocalStorage)**: Bring Your Own Key (BYOK) model. Enter your Azure AI Foundry / OpenAI key securely in the UI; it stays saved in your browser's `localStorage` and is never persisted on the server.
- **Instant AI Title Summaries**: Click "AI Summary" on any search result to generate an instant, engaging overview of the film or TV show.
- **Interactive Data Explorer**: Instant client-side filtering, sorting, pagination, query suggestions, and SQL query export.
- **Containerized & Cloud-Ready**: Fully Dockerized with Gunicorn and pre-cached DuckDB Azure extensions.

---

## 🚀 Quick Start

### 1. Run Locally (Python Virtualenv)

```bash
# Clone the repository
git clone https://github.com/sarathavasarala/natural-language-imdb.git
cd natural-language-imdb

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the application
python run.py
```

The app will be live at `http://localhost:5001`. Open the ⚙️ **API Settings** modal in the navbar to enter your Azure OpenAI / Foundry credentials.

---

### 2. Run with Docker

```bash
docker compose up --build
```

Access the application at `http://localhost:5001`.

---

## ☁️ Azure Cloud Deployment

The application is deployed to an isolated Azure Resource Group (`rg-imdb-intelligence`):

1. **Storage Account**: `stimdbdataeastus` with blob container `imdb-data`.
2. **App Service Plan**: `asp-imdb-intelligence` (Linux).
3. **Web App**: `imdb-intelligence-app.azurewebsites.net`.

### Deploy Updates to Azure Web App

```bash
# Create deployment package
zip -r deploy.zip app run.py config.py requirements.txt -x "*.DS_Store" "*__pycache__*"

# Deploy to Azure
az webapp deploy \
  --name imdb-intelligence-app \
  --resource-group rg-imdb-intelligence \
  --src-path deploy.zip \
  --type zip
```

---

## 🔄 Automated ETL Pipeline (IMDb TSVs ➔ Azure Parquet)

To download the latest daily dataset from IMDb (`https://datasets.imdbws.com/`) and convert directly to ZSTD-compressed Parquet in Azure Blob Storage:

```bash
python scripts/etl_imdb_to_parquet.py \
  --connection-string "<YOUR_AZURE_STORAGE_CONNECTION_STRING>" \
  --container "imdb-data"
```

To refresh specific tables only:
```bash
python scripts/etl_imdb_to_parquet.py --tables titles ratings
```

---

## 📊 Dataset Schema

| Table | Remote URI | Description |
| :--- | :--- | :--- |
| **`titles`** | `azure://imdb-data/titles.parquet` | All movies, series, episodes, release years, runtime, genres |
| **`ratings`** | `azure://imdb-data/ratings.parquet` | Weighted average IMDb ratings and vote counts |
| **`people`** | `azure://imdb-data/people.parquet` | Cast and crew names, birth and death years |
| **`crew`** | `azure://imdb-data/crew.parquet` | Principal cast/crew roles, characters, and billing order |
| **`episodes`** | `azure://imdb-data/episodes.parquet` | TV series season and episode number relationships |
| **`akas`** | `azure://imdb-data/akas.parquet` | International localized and alternative titles |

---

## 💡 Example Queries

- *"Find movies where Robert De Niro and Al Pacino acted together"*
- *"Highest rated sci-fi movies from the 2020s with over 100,000 votes"*
- *"List all episodes of The Office TV show sorted by rating"*
- *"Best movies starring Tom Hanks released before 2000"*
- *"Directors who made both horror and comedy films"*

---

## 📄 License

IMDb datasets are provided for personal and non-commercial use only by IMDb.
