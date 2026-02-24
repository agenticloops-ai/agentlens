"""Backward-compatibility re-exports.

All parsers have moved to ``agentlens.providers``.
This module re-exports the key symbols so existing code keeps working.
"""

from agentlens.providers import PluginRegistry, ProviderMeta, ProviderPlugin
from agentlens.providers.anthropic import AnthropicPlugin
from agentlens.providers.openai import OpenAICompletionsPlugin, OpenAIPlugin

# Aliases for backward compatibility
BaseParser = ProviderPlugin
AnthropicParser = AnthropicPlugin
OpenAIParser = OpenAIPlugin
OpenAICompletionsParser = OpenAICompletionsPlugin
ParserRegistry = PluginRegistry

__all__ = [
    "AnthropicParser",
    "BaseParser",
    "OpenAICompletionsParser",
    "OpenAIParser",
    "ParserRegistry",
    "ProviderMeta",
]
