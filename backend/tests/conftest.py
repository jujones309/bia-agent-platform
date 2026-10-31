import os

# Set before any test module imports bia.api.main, which validates settings on import.
# Process variables take precedence over backend/.env, so tests never see real secrets.
os.environ["OPENAI_API_KEY"] = "test-openai-key"
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test"
os.environ["ENVIRONMENT"] = "test"
os.environ["LOG_LEVEL"] = "INFO"
