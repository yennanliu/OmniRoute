"""Request/response schemas for the OpenAI-compatible surface."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChatCompletionRequest(BaseModel):
    # Pass through any extra OpenAI params (temperature, stream, ...) untouched.
    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[dict[str, Any]]

    def passthrough_params(self) -> dict[str, Any]:
        """Fields to forward to the completer, minus the ones we handle explicitly."""
        data = self.model_dump(exclude_none=True)
        data.pop("model", None)
        data.pop("messages", None)
        return data


class CreateKeyRequest(BaseModel):
    max_budget: float | None = Field(default=None, description="USD spend cap; null = unlimited")
    models: list[str] | None = Field(default=None, description="Allowed models; null = all")


class KeyResponse(BaseModel):
    key: str
    max_budget: float | None
    spend: float
    models: list[str] | None


class SpendResponse(BaseModel):
    key: str
    spend: float
    max_budget: float | None
