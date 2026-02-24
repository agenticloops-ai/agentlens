"""Anthropic pricing tables.

All prices are per 1M tokens in USD.
"""

ANTHROPIC_PRICING: dict[str, dict[str, float]] = {
    # Claude 4.x family
    "claude-opus-4": {"input": 15.00, "output": 75.00, "cache_write": 18.75, "cache_read": 1.50},
    "claude-sonnet-4": {"input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30},
    # Claude 4.5 family (haiku)
    "claude-haiku-4": {"input": 0.80, "output": 4.00, "cache_write": 1.00, "cache_read": 0.08},
    # Claude 3.5 family
    "claude-3.5-sonnet": {"input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30},
    "claude-3.5-haiku": {"input": 0.80, "output": 4.00, "cache_write": 1.00, "cache_read": 0.08},
    "claude-haiku-3.5": {"input": 0.80, "output": 4.00, "cache_write": 1.00, "cache_read": 0.08},
    # Claude 3 family
    "claude-3-opus": {"input": 15.00, "output": 75.00, "cache_write": 18.75, "cache_read": 1.50},
}
