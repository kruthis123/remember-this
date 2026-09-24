import os
from langfuse import get_client
from pydantic_ai.agent import Agent

from remember_this.config import get_settings

Settings = get_settings()

os.environ.setdefault("LANGFUSE_PUBLIC_KEY", Settings.langfuse_public_key.get_secret_value())
os.environ.setdefault("LANGFUSE_SECRET_KEY", Settings.langfuse_secret_key.get_secret_value())
os.environ.setdefault("LANGFUSE_BASE_URL", Settings.langfuse_base_url)

langfuse = get_client()

if langfuse.auth_check():
    print("Langfuse client is authenticated and ready!")
else:
    print("Authentication failed. Please check your credentials and host")

Agent.instrument_all()

def flush():
    langfuse.flush()