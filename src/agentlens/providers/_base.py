"""Abstract base class for provider plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from agentlens.models import LLMRequest, RawCapture, TokenUsage


@dataclass(frozen=True)
class ProviderMeta:
    """Provider metadata exposed to the registry and frontend."""

    name: str  # e.g. "openai", "anthropic" — stored in DB
    display_name: str  # e.g. "OpenAI", "Anthropic"
    color: str  # hex color for UI, e.g. "#22c55e"


@dataclass(frozen=True)
class EndpointPattern:
    """URL pattern that a provider plugin handles."""

    host: str  # substring match, e.g. "api.openai.com"
    path: str  # exact or suffix match, e.g. "/v1/responses"


class ProviderPlugin(ABC):
    """Single interface for a provider plugin.

    Owns detection, parsing, pricing, and metadata.
    """

    @property
    @abstractmethod
    def meta(self) -> ProviderMeta:
        """Return metadata about this plugin's provider."""
        ...

    @property
    @abstractmethod
    def endpoints(self) -> list[EndpointPattern]:
        """URL patterns this plugin handles (used for traffic detection + can_parse)."""
        ...

    @property
    def path_only_patterns(self) -> list[str]:
        """Path-only patterns for self-hosted/proxy scenarios (no host check)."""
        return [ep.path for ep in self.endpoints]

    @property
    def pricing(self) -> dict[str, dict[str, float]]:
        """Model pricing table {model_prefix: {input, output, ...}}."""
        return {}

    @abstractmethod
    def parse(
        self,
        raw: RawCapture,
        duration_ms: float | None = None,
        ttft_ms: float | None = None,
    ) -> LLMRequest:
        """Parse a raw capture into a generic LLMRequest."""
        ...

    def can_parse(self, raw: RawCapture) -> bool:
        """Default: match request_url against self.endpoints."""
        url = raw.request_url
        for ep in self.endpoints:
            if ep.host in url and ep.path in url:
                return True
        return False

    def estimate_cost(self, model: str, usage: TokenUsage) -> float | None:
        """Estimate cost using this plugin's pricing table and prefix matching.

        Handles input, output, cache_write, and cache_read pricing keys.
        """
        pricing = self.pricing
        if not pricing:
            return None

        for prefix in sorted(pricing.keys(), key=len, reverse=True):
            if model.startswith(prefix):
                p = pricing[prefix]
                cost = (
                    usage.input_tokens * p.get("input", 0)
                    + usage.output_tokens * p.get("output", 0)
                    + usage.cache_creation_input_tokens * p.get("cache_write", 0)
                    + usage.cache_read_input_tokens * p.get("cache_read", 0)
                ) / 1_000_000
                return cost

        return None
