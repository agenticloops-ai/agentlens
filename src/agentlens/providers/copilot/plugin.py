"""GitHub Copilot plugins — reuse OpenAI/Anthropic parsing with Copilot-specific detection."""

from __future__ import annotations

from agentlens.models import RawCapture

from .._base import EndpointPattern, ProviderMeta
from ..anthropic.plugin import AnthropicPlugin
from ..openai.completions import OpenAICompletionsPlugin
from ..openai.plugin import OpenAIPlugin

COPILOT_HOSTS = [
    "api.individual.githubcopilot.com",
    "api.business.githubcopilot.com",
    "api.enterprise.githubcopilot.com",
]

_COPILOT_META = ProviderMeta(name="github-copilot", display_name="GitHub Copilot", color="#6e40c9")


def _is_copilot_url(url: str, path: str) -> bool:
    return any(host in url for host in COPILOT_HOSTS) and path in url


class GithubCopilotPlugin(OpenAIPlugin):
    """Plugin for GitHub Copilot using the Responses API (/responses)."""

    @property
    def meta(self) -> ProviderMeta:
        return _COPILOT_META

    @property
    def endpoints(self) -> list[EndpointPattern]:
        return [EndpointPattern(host, "/responses") for host in COPILOT_HOSTS]

    @property
    def path_only_patterns(self) -> list[str]:
        return []

    def can_parse(self, raw: RawCapture) -> bool:
        return _is_copilot_url(raw.request_url, "/responses")


class GithubCopilotCompletionsPlugin(OpenAICompletionsPlugin):
    """Plugin for GitHub Copilot using the Chat Completions API (/v1/chat/completions)."""

    @property
    def meta(self) -> ProviderMeta:
        return _COPILOT_META

    @property
    def endpoints(self) -> list[EndpointPattern]:
        return [EndpointPattern(host, "/v1/chat/completions") for host in COPILOT_HOSTS]

    @property
    def path_only_patterns(self) -> list[str]:
        return []

    def can_parse(self, raw: RawCapture) -> bool:
        return _is_copilot_url(raw.request_url, "/v1/chat/completions")


class GithubCopilotAnthropicPlugin(AnthropicPlugin):
    """Plugin for GitHub Copilot using the Anthropic Messages API (/v1/messages)."""

    @property
    def meta(self) -> ProviderMeta:
        return _COPILOT_META

    @property
    def endpoints(self) -> list[EndpointPattern]:
        return [EndpointPattern(host, "/v1/messages") for host in COPILOT_HOSTS]

    @property
    def path_only_patterns(self) -> list[str]:
        return []

    def can_parse(self, raw: RawCapture) -> bool:
        return _is_copilot_url(raw.request_url, "/v1/messages")
