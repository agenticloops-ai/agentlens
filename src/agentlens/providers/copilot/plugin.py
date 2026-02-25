"""GitHub Copilot plugins — reuse OpenAI/Anthropic parsing with Copilot-specific detection."""

from __future__ import annotations

from agentlens.models import RawCapture

from .._base import EndpointPattern, ProviderMeta
from ..anthropic.plugin import AnthropicPlugin
from ..gemini.plugin import GeminiPlugin
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
    def priority(self) -> int:
        return 10

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
    """Plugin for GitHub Copilot using the Chat Completions API.

    Copilot routes requests to both ``/v1/chat/completions`` and
    ``/chat/completions`` (used for Gemini models among others).
    """

    @property
    def priority(self) -> int:
        return 10

    @property
    def meta(self) -> ProviderMeta:
        return _COPILOT_META

    @property
    def endpoints(self) -> list[EndpointPattern]:
        eps = []
        for host in COPILOT_HOSTS:
            eps.append(EndpointPattern(host, "/v1/chat/completions"))
            eps.append(EndpointPattern(host, "/chat/completions"))
        return eps

    @property
    def path_only_patterns(self) -> list[str]:
        return []

    def can_parse(self, raw: RawCapture) -> bool:
        return _is_copilot_url(raw.request_url, "/chat/completions")


class GithubCopilotAnthropicPlugin(AnthropicPlugin):
    """Plugin for GitHub Copilot using the Anthropic Messages API (/v1/messages)."""

    @property
    def priority(self) -> int:
        return 10

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


class GithubCopilotGeminiPlugin(GeminiPlugin):
    """Plugin for GitHub Copilot using the Gemini API (:generateContent / :streamGenerateContent)."""

    @property
    def priority(self) -> int:
        return 10

    @property
    def meta(self) -> ProviderMeta:
        return _COPILOT_META

    @property
    def endpoints(self) -> list[EndpointPattern]:
        eps = []
        for host in COPILOT_HOSTS:
            eps.append(EndpointPattern(host, ":generateContent"))
            eps.append(EndpointPattern(host, ":streamGenerateContent"))
        return eps

    @property
    def path_only_patterns(self) -> list[str]:
        return []

    def can_parse(self, raw: RawCapture) -> bool:
        url = raw.request_url
        return any(host in url for host in COPILOT_HOSTS) and (
            ":generateContent" in url or ":streamGenerateContent" in url
        )
