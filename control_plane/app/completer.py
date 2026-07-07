"""The completion backend.

`Completer` is the seam between our gateway and LiteLLM. Production wires in
`LiteLLMCompleter` (routing, load-balancing, fallbacks); tests substitute a
fake, so the suite never touches the network or needs provider keys.
"""

from __future__ import annotations

from typing import Any, Protocol


class Completer(Protocol):
    async def acomplete(
        self, *, model: str, messages: list[dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]:
        """Return an OpenAI-shaped chat-completion response as a dict."""
        ...


class LiteLLMCompleter:
    """Wraps `litellm.Router` for multi-provider routing + failover.

    The Router is built lazily on first use so importing the app never requires
    provider credentials.
    """

    def __init__(
        self, model_list: list[dict[str, Any]], router_settings: dict[str, Any] | None = None
    ) -> None:
        self._model_list = model_list
        self._router_settings = router_settings or {}
        self._router: Any | None = None

    def _get_router(self) -> Any:
        if self._router is None:
            from litellm import Router  # imported lazily; heavy dependency

            self._router = Router(model_list=self._model_list, **self._router_settings)
        return self._router

    async def acomplete(
        self, *, model: str, messages: list[dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]:
        response = await self._get_router().acompletion(model=model, messages=messages, **kwargs)
        # LiteLLM returns a pydantic model; normalize to a plain dict.
        return response.model_dump() if hasattr(response, "model_dump") else dict(response)
