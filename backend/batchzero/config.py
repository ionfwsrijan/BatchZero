"""Environment-driven configuration for BatchZero."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- FalkorDB ---
    falkordb_host: str = "localhost"
    falkordb_port: int = 6379
    falkordb_password: str | None = None

    # --- Tenants (one FalkorDB graph per agency/tenant) ---
    tenant_graph: str = "pmph_ops"
    training_tenant_graph: str = "training_academy"

    # --- LLM ---
    llm_provider: str = "mock"  # groq | openai | mock
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    openai_base_url: str = "https://api.groq.com/openai/v1"
    openai_api_key: str | None = None
    llm_temperature: float = 0.1

    # --- Agent ---
    max_agent_steps: int = 14
    agent_verbose: bool = True

    # --- Server ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "*"

    @property
    def resolved_llm_provider(self) -> str:
        """Fall back to mock whenever no credentials exist, so demos never break."""
        provider = (self.llm_provider or "mock").lower()
        if provider == "groq" and not (self.groq_api_key or self.openai_api_key):
            return "mock"
        if provider == "openai" and not self.openai_api_key:
            return "mock"
        return provider


@lru_cache
def get_settings() -> Settings:
    return Settings()
