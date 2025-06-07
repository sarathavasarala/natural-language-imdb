# Configuration Template for IMDb Intelligence
# Copy this file to config.py and fill in your actual values

# Azure OpenAI Configuration
AZURE_OPENAI_API_KEY = "your_azure_openai_api_key_here"
AZURE_OPENAI_API_VERSION = "2025-01-01-preview"  # Or latest available version
AZURE_OPENAI_ENDPOINT = "https://your-resource-name.openai.azure.com/"
AZURE_OPENAI_MODEL = "gpt-4.1"  # Or your deployed model name

# Database Configuration
DATABASE_PATH = "db/imdb.db"

# Application Settings
DEBUG = False
SECRET_KEY = "your-secret-key-here-change-this-in-production"
HOST = "0.0.0.0"
PORT = 5000

# Logging Configuration
LOG_LEVEL = "INFO"
LOG_FILE = "app.log"

# Performance Settings
MAX_QUERY_LENGTH = 500
DEFAULT_RESULT_LIMIT = 50
QUERY_TIMEOUT = 30

# Security Settings
RATE_LIMIT_PER_MINUTE = 60
ENABLE_SQL_VALIDATION = True

# Feature Flags
ENABLE_QUERY_HISTORY = True
ENABLE_STATISTICS = True
ENABLE_API_ENDPOINTS = True

# External APIs (for future enhancements)
TMDB_API_KEY = "your_tmdb_api_key_here"  # For movie posters
OMDB_API_KEY = "your_omdb_api_key_here"  # For additional metadata
