# Configuration Template for IMDb Text-to-SQL Search
# Copy this file to config.py and fill in your credentials or set environment variables.
import os

# Azure OpenAI / AI Foundry settings
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "your_azure_openai_api_key_here")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "https://your-resource.openai.azure.com")
AZURE_OPENAI_MODEL = os.getenv("AZURE_OPENAI_MODEL", "gpt-5.4")

# Azure Blob Storage settings for Parquet datasets
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "your_azure_storage_connection_string_here")
AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "imdb-data")

# Legacy database path (optional local SQLite fallback)
DATABASE_PATH = os.getenv("DATABASE_PATH", "db/imdb.db")
