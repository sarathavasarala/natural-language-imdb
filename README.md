# IMDb Intelligence — Natural Language Text-to-SQL Search

An intelligent search engine and analytical dashboard for the entire 10M+ IMDb catalog. Converts natural language questions into ANSI SQL queries via **Azure AI Foundry / OpenAI** and executes them against a local, read-only **DuckDB** database synchronized from Azure Blob Storage.

![IMDb Intelligence Interface](natural%20language%20imdb.jpeg)

🌐 **Live Production Application:** [https://imdb-intelligence-app.azurewebsites.net](https://imdb-intelligence-app.azurewebsites.net)

---

## 🌟 Key Features

- **Projectionist's Digital Command Console**: Modern cinematic OLED dark aesthetic (`#07090E`), IMDb luminous amber accents (`#F5C518`), ambient backlight aura, and high-legibility typography (`Outfit` + `JetBrains Mono`).
- **Natural Language to SQL**: Converts complex conversational questions into optimized ANSI SQL queries via Azure OpenAI (`gpt-4o`, `gpt-5.4`).
- **Local DuckDB Query Engine**: Downloads a compact database artifact from Azure Blob Storage once, then serves fast local joins without a managed database.
- **Client-Side Key Management (LocalStorage)**: Bring Your Own Key (BYOK) model. Enter your Azure AI Foundry / OpenAI key securely in the UI modal; it is saved in browser `localStorage` and sent over HTTPS headers without persisting secrets on the server.
- **Real-Time Telemetry & SQL Inspector**: Monospace performance badges (query execution latency in seconds, row count) and an interactive, syntax-highlighted SQL drawer with 1-click clipboard copy.
- **Interactive Multi-Filter Drawer**: Filter results dynamically by release year ranges, IMDb rating thresholds, and active genre tags with live count badges.
- **Instant AI Title Summaries**: 1-click spoiler-free AI synopsis and cultural trivia for any search result.
- **Keyboard-First Workflow**: Press `/` anywhere to focus the search bar; press `Escape` or click `✕` to clear.

---

## 🚀 Quick Start (Local Development)

### 1. Run with Python Virtual Environment

```bash
# Clone the repository
git clone https://github.com/sarathavasarala/natural-language-imdb.git
cd natural-language-imdb

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the local development server
python run.py
```

Open `http://localhost:5001`. Click **API Settings** in the top navigation bar to configure your Azure AI Foundry / OpenAI credentials.

---

### 2. Run with Docker Compose

```bash
docker compose up --build
```

Access the application at `http://localhost:5001`.

---

## 🚀 CI/CD & Deployment Architecture

### 1. Automated Deployment via GitHub Actions (Recommended)

Every push to the `main` branch automatically triggers the GitHub Actions workflow at [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml):

```
┌──────────────────────────┐       ┌──────────────────────────────┐       ┌──────────────────────────────┐
│  git push origin main    │ ────> │   GitHub Actions CI/CD       │ ────> │   Azure App Service (Linux)  │
│  (Code + Templates + CSS)│       │   - Build & verification     │       │   imdb-intelligence-app      │
│                          │       │   - Zip artifact packaging   │       │   .azurewebsites.net         │
└──────────────────────────┘       └──────────────────────────────┘       └──────────────────────────────┘
```

#### How to configure GitHub Actions Secrets for automatic deployment:
1. Download the publish profile XML from the Azure Portal or Azure CLI:
   ```bash
   az webapp deployment list-publishing-profiles \
     --name imdb-intelligence-app \
     --resource-group rg-imdb-intelligence \
     --xml
   ```
2. In your GitHub repository, go to **Settings** ➔ **Secrets and variables** ➔ **Actions**.
3. Create a new repository secret named `AZURE_WEBAPP_PUBLISH_PROFILE` and paste the XML contents.
4. Any future `git push origin main` will automatically build and deploy the update live in ~1-2 minutes!

---

### 2. Manual Deployment via Azure CLI

To deploy directly from your local terminal:

```bash
# Create deployment package
zip -r deploy.zip app run.py config.template.py requirements.txt -x "*.DS_Store" "*__pycache__*"

# Deploy to Azure App Service
az webapp deploy \
  --name imdb-intelligence-app \
  --resource-group rg-imdb-intelligence \
  --src-path deploy.zip \
  --type zip
```

---

## 🔄 Dataset refresh

To refresh Parquet datasets directly from IMDb's official data dumps (`https://datasets.imdbws.com/`) into Azure Blob Storage:

```bash
python scripts/etl_imdb_to_parquet.py \
  --connection-string "<YOUR_AZURE_STORAGE_CONNECTION_STRING>" \
  --container "imdb-data"
```

To refresh specific tables only:
```bash
python scripts/etl_imdb_to_parquet.py --tables titles ratings
```

After refreshing the Parquet source files, build and upload the database artifact:

```bash
python scripts/build_duckdb_database.py \
  --connection-string "<YOUR_AZURE_STORAGE_CONNECTION_STRING>" \
  --container "imdb-data"
```

The web app downloads `imdb.duckdb` to persistent local storage when its Blob
ETag changes. Restart the App Service after publishing a refreshed artifact so
each worker opens the new database.

---

## 📊 Dataset Schema

| Table | Source artifact | Schema Fields |
| :--- | :--- | :--- |
| **`titles`** | `azure://imdb-data/titles.parquet` | `title_id`, `type`, `primary_title`, `original_title`, `is_adult`, `premiered`, `ended`, `runtime_minutes`, `genres` |
| **`ratings`** | `azure://imdb-data/ratings.parquet` | `title_id`, `rating`, `votes` |
| **`people`** | `azure://imdb-data/people.parquet` | `person_id`, `name`, `born`, `died` |
| **`crew`** | `azure://imdb-data/crew.parquet` | `title_id`, `person_id`, `category`, `job`, `characters` |
| **`episodes`** | `azure://imdb-data/episodes.parquet` | `episode_title_id`, `show_title_id`, `season_number`, `episode_number` |
| **`akas`** | `azure://imdb-data/akas.parquet` | `title_id`, `title`, `region`, `language`, `types`, `attributes`, `is_original_title` |

---

## 💡 Example Natural Language Queries

- *"Movies where Leonardo DiCaprio and Kate Winslet worked together"*
- *"Highest rated sci-fi movies from 2010s"*
- *"Christopher Nolan movies"*
- *"Best movies from 2020 with over 50,000 votes"*
- *"Directors who made both horror and comedy movies"*
- *"Draw a chart of Tom Hanks movies by year"*

---

## 📄 License

IMDb datasets are provided for personal and non-commercial use only by IMDb.
