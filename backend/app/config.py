"""
Application Configuration — Pydantic Settings

Reads environment variables from .env file and provides
typed access throughout the application.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Literal


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- LLM Configuration ---
    llm_provider: Literal["openai", "gemini"] = Field(
        default="openai",
        description="LLM provider to use: 'openai' or 'gemini'"
    )

    # OpenAI
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key"
    )
    openai_model: str = Field(
        default="gpt-4o",
        description="OpenAI model identifier"
    )

    # Google Gemini
    google_api_key: str = Field(
        default="",
        description="Google Gemini API key"
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        description="Gemini model identifier"
    )

    # --- Actor-Critic Pipeline ---
    max_retries: int = Field(
        default=2,
        description="Max retry cycles for the Actor-Critic loop"
    )

    # --- Server ---
    backend_host: str = Field(default="0.0.0.0")
    backend_port: int = Field(default=8001)

    # --- CORS ---
    frontend_url: str = Field(
        default="http://localhost:5173",
        description="Frontend origin for CORS"
    )

    # --- Data Export ---
    data_volume_path: str = Field(
        default="./data-volumes",
        description="Path to the directory where generated CSVs are saved"
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


# Singleton instance
settings = Settings()
