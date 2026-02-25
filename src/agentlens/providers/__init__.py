"""Provider plugin auto-discovery and registry."""

from __future__ import annotations

import importlib
import pkgutil

from agentlens.models import RawCapture

from ._base import EndpointPattern, ProviderMeta, ProviderPlugin


def _discover_plugins() -> list[ProviderPlugin]:
    """Scan all subpackages of providers/, import them, collect ProviderPlugin instances."""
    plugins: list[ProviderPlugin] = []
    seen_classes: set[type] = set()

    # Iterate over immediate sub-packages (openai/, anthropic/, etc.)
    for importer, modname, ispkg in pkgutil.iter_modules(__path__, __name__ + "."):
        if modname.endswith("._base"):
            continue
        module = importlib.import_module(modname)

        # Collect all ProviderPlugin subclasses exported by the module
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, ProviderPlugin)
                and attr is not ProviderPlugin
                and attr not in seen_classes
            ):
                seen_classes.add(attr)
                plugins.append(attr())

    return plugins


def _clean_path(path: str) -> str:
    """Strip query string from path."""
    return path.split("?", 1)[0]


class PluginRegistry:
    """Registry built automatically from discovered plugins.

    Replaces both ``ParserRegistry`` and ``provider_detect.py``.
    """

    def __init__(self, plugins: list[ProviderPlugin]) -> None:
        self._plugins = sorted(plugins, key=lambda p: p.priority, reverse=True)

    # -- Parser dispatch (replaces ParserRegistry) --

    def get_plugin(self, raw: RawCapture) -> ProviderPlugin | None:
        """Find the first plugin that can handle this raw capture."""
        for plugin in self._plugins:
            if plugin.can_parse(raw):
                return plugin
        return None

    def get_providers(self) -> list[dict[str, str]]:
        """Return deduplicated metadata for all registered providers."""
        seen: set[str] = set()
        providers: list[dict[str, str]] = []
        for plugin in self._plugins:
            meta = plugin.meta
            if meta.name not in seen:
                seen.add(meta.name)
                providers.append(
                    {
                        "name": meta.name,
                        "display_name": meta.display_name,
                        "color": meta.color,
                    }
                )
        return providers

    def get_provider_meta(self, name: str) -> ProviderMeta | None:
        """Look up metadata by provider name."""
        for plugin in self._plugins:
            if plugin.meta.name == name:
                return plugin.meta
        return None

    # -- Provider detection (replaces provider_detect.py) --

    def detect_provider(self, host: str, path: str, headers: dict[str, str]) -> str | None:
        """Detect provider from hostname + path.

        Only returns a provider name when the request targets a known LLM inference
        endpoint. Built from plugin endpoints — no separate mapping needed.
        """
        clean = _clean_path(path)

        # Check host + path combinations from all plugins
        for plugin in self._plugins:
            for ep in plugin.endpoints:
                if ep.host in host and (clean == ep.path or clean.endswith(ep.path)):
                    return plugin.meta.name

        # Fallback: path-only matching (self-hosted proxies / gateway rewrites)
        for plugin in self._plugins:
            for pattern in plugin.path_only_patterns:
                if clean == pattern or clean.endswith(pattern):
                    return plugin.meta.name

        return None

    def is_llm_request(self, host: str, path: str, headers: dict[str, str]) -> bool:
        """Return True if this looks like an LLM API request we should capture."""
        return self.detect_provider(host, path, headers) is not None

    @classmethod
    def default(cls) -> PluginRegistry:
        """Create a registry with all auto-discovered plugins."""
        return cls(_discover_plugins())


# Convenience re-exports
__all__ = [
    "EndpointPattern",
    "PluginRegistry",
    "ProviderMeta",
    "ProviderPlugin",
]
