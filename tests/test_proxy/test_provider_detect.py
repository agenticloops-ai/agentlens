"""Tests for provider detection via PluginRegistry."""

from agentlens.providers import PluginRegistry

# Use a shared registry instance for all tests
_registry = PluginRegistry.default()


def detect_provider(host, path, headers):
    return _registry.detect_provider(host, path, headers)


def is_llm_request(host, path, headers):
    return _registry.is_llm_request(host, path, headers)


class TestDetectProvider:
    def test_detect_openai_by_host(self):
        result = detect_provider("api.openai.com", "/v1/chat/completions", {})
        assert result == "openai"

    def test_detect_anthropic_by_host(self):
        result = detect_provider("api.anthropic.com", "/v1/messages", {})
        assert result == "anthropic"

    def test_detect_openai_by_path(self):
        result = detect_provider("my-proxy.local", "/v1/chat/completions", {})
        assert result == "openai"

    def test_detect_anthropic_by_path(self):
        result = detect_provider("my-proxy.local", "/v1/messages", {})
        assert result == "anthropic"

    def test_detect_unknown(self):
        result = detect_provider("example.com", "/api/other", {})
        assert result is None

    def test_host_path_must_both_match_for_known_hosts(self):
        """Known host + wrong path should NOT match."""
        result = detect_provider("api.anthropic.com", "/api/eval/sdk-123", {})
        assert result is None

    def test_anthropic_internal_endpoints_not_captured(self):
        """Internal SDK endpoints on api.anthropic.com should not be captured."""
        assert detect_provider("api.anthropic.com", "/api/oauth/client_data", {}) is None
        assert detect_provider("api.anthropic.com", "/api/event_logging/batch", {}) is None
        assert detect_provider("api.anthropic.com", "/v1/mcp_servers", {}) is None
        assert detect_provider("api.anthropic.com", "/v1/messages/count_tokens", {}) is None
        assert detect_provider("api.anthropic.com", "/api/hello", {}) is None

    def test_anthropic_messages_with_query_params(self):
        """Messages endpoint with query params like ?beta=true should match."""
        result = detect_provider("api.anthropic.com", "/v1/messages?beta=true", {})
        assert result == "anthropic"

    def test_path_suffix_matching(self):
        """Gateway-style prefix paths should still match."""
        result = detect_provider("my-gateway.local", "/proxy/v1/chat/completions", {})
        assert result == "openai"

    def test_anthropic_path_suffix_matching(self):
        result = detect_provider("my-gateway.local", "/proxy/v1/messages", {})
        assert result == "anthropic"

    def test_headers_alone_not_sufficient(self):
        """Headers alone should NOT trigger detection — too many false positives."""
        headers = {"x-api-key": "sk-ant-abc123"}
        result = detect_provider("some-unknown-host.com", "/api/generate", headers)
        assert result is None

        headers2 = {"authorization": "Bearer sk-proj-abc123xyz"}
        result2 = detect_provider("some-unknown-host.com", "/api/generate", headers2)
        assert result2 is None


class TestIsLlmRequest:
    def test_is_llm_request_true(self):
        assert is_llm_request("api.openai.com", "/v1/chat/completions", {}) is True
        assert is_llm_request("api.anthropic.com", "/v1/messages", {}) is True
        assert is_llm_request("proxy.local", "/v1/chat/completions", {}) is True

    def test_is_llm_request_false(self):
        assert is_llm_request("example.com", "/api/other", {}) is False
        assert is_llm_request("google.com", "/search", {}) is False
        assert is_llm_request("cdn.example.com", "/assets/main.js", {}) is False

    def test_is_llm_request_false_for_internal_endpoints(self):
        assert is_llm_request("api.anthropic.com", "/api/eval/sdk-123", {}) is False
        assert is_llm_request("api.anthropic.com", "/v1/messages/count_tokens", {}) is False
