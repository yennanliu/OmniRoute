"""Application settings and the default model routing table."""

from __future__ import annotations

from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OMNIROUTE_", extra="ignore")

    master_key: str = "sk-omni-master-dev"  # admin key for provisioning; override in prod
    # None -> in-memory store. Local dev: "sqlite:///omniroute.db".
    # Prod: "postgresql+psycopg://user:pw@host/omniroute".
    database_url: str | None = None


def default_model_list() -> list[dict[str, Any]]:
    """Two deployments of `gpt-4o` (primary + backup) so the Router can fail over.

    Keys are read from the environment at Router build time by LiteLLM.
    """
    return [
        {
            "model_name": "gpt-4o",
            "litellm_params": {
                "model": "openai/gpt-4o",
                "api_key": "os.environ/OPENAI_API_KEY",
                "rpm": 1000,
            },
            "model_info": {"id": "openai-4o-primary"},
        },
        {
            "model_name": "claude-sonnet",
            "litellm_params": {
                "model": "anthropic/claude-3-5-sonnet-latest",
                "api_key": "os.environ/ANTHROPIC_API_KEY",
            },
            "model_info": {"id": "anthropic-sonnet"},
        },
    ]
