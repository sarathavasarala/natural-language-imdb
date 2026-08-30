# Configuration Template for IMDb Text-to-SQL Search
# Copy this file to config.py and fill in your credentials or set environment variables.
import os

# Azure AI Foundry / Azure OpenAI settings
# Supports both:
# 1. Azure AI Foundry: https://<resource>.services.ai.azure.com/openai/v1
# 2. Classic Azure OpenAI: https://<resource>.openai.azure.com
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "your_azure_api_key_here")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "https://your-resource.services.ai.azure.com/openai/v1")
AZURE_OPENAI_MODEL = os.getenv("AZURE_OPENAI_MODEL", "gpt-5.6-luna")

# Azure Blob Storage settings for the generated DuckDB artifact and source Parquet files
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "your_azure_storage_connection_string_here")
AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "imdb-data")
DUCKDB_BLOB_NAME = os.getenv("DUCKDB_BLOB_NAME", "imdb.duckdb")
DUCKDB_DATABASE_PATH = os.getenv("DUCKDB_DATABASE_PATH", "db/imdb.duckdb")

# Legacy database path (optional local SQLite fallback)
DATABASE_PATH = os.getenv("DATABASE_PATH", "db/imdb.db")
