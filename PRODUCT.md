# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Film buffs, movie lovers, film students, entertainment writers, and researchers seeking deep cinematic discovery, movie/TV facts, cast/crew collaborations, and statistical insights across the entire IMDb catalog.

## Product Purpose

IMDb Intelligence is a conversational search engine and analytical discovery tool for the IMDb dataset. It allows users to ask natural language questions ("Movies where Leonardo DiCaprio and Kate Winslet worked together", "Highest rated 90s sci-fi movies") and instantly receive structured results powered by Azure AI Foundry text-to-SQL running against 1.3GB of remote ZSTD Parquet tables via DuckDB.

## Positioning

Unlike generic search bars or static filter menus, IMDb Intelligence converts open-ended natural conversational prompts into ANSI SQL queries executed directly in-flight against cloud-hosted Parquet data lake files, accompanied by transparent SQL generation and on-demand AI spoiler-free narrative summaries.

## Operating Context

Used across desktop and mobile browsers for quick trivia lookups, research deep-dives, movie night discovery, and analytical queries. Works seamlessly with Bring-Your-Own-Key (BYOK) stored securely in browser `localStorage`.

## Capabilities and Constraints

- **Natural Language to SQL**: Converts questions into optimized DuckDB queries using Azure OpenAI (`gpt-4o`, `gpt-5.4`).
- **Zero Local Disk Parquet Engine**: Connects via HTTP range requests to Azure Blob Storage Parquet views (`titles`, `ratings`, `people`, `crew`, `episodes`, `akas`).
- **Interactive Data Table & Exploration**: Sorting, searching, pagination, dynamic genre/year/rating refinement, shareable URL query states (`?q=...`), and direct IMDb external links.
- **On-Demand AI Summaries**: Provides contextual summaries for individual movies or shows via modal.
- **Client-Side Key Management**: Secure `localStorage` credential persistence for Azure OpenAI endpoint, API key, model deployment, and version.

## Brand Commitments

- **Name**: IMDb Intelligence
- **Aesthetic Direction**: Cinematic dark aesthetic with deep OLED blacks (`#0B0D13` / `#12151E`), IMDb gold/amber accents (`#F5C518` / `#FFD13B`), subtle cinematic glowing borders, backdrop blur glassmorphism cards, and high-legibility modern typography.

## Evidence on Hand

- Real IMDb Parquet schema in DuckDB views (`titles`, `ratings`, `people`, `crew`, `episodes`, `akas`).
- Live backend API routes: `/api/search`, `/api/generate_summary`, `/api/title_info`, `/api/suggestions`.
- Frontend static assets: `app/static/favicon.png`, `app/templates/index.html`.

## Product Principles

1. **Cinematic First Impression**: Every screen feels like stepping into a high-end film festival theater or premiere terminal — rich, dark, polished, and atmospheric.
2. **Effortless Discovery**: Natural language search is front and center with intelligent suggestions, instant feedback, and zero friction.
3. **Transparent Intelligence**: Users can see and inspect the generated SQL query and execution performance anytime without cluttering the main cinematic view.
4. **Fast, Dense, Responsive**: Data presentation is scannable, filterable, and responsive across any device with silky-smooth micro-interactions.
