"""Gemini pricing tables.

All prices are per 1M tokens in USD.
Prices use the standard paid tier for prompts ≤200K tokens.
Source: https://ai.google.dev/gemini-api/docs/pricing
"""

GEMINI_PRICING: dict[str, dict[str, float]] = {
    # Gemini 3 family
    "gemini-3.1-pro": {"input": 2.00, "output": 12.00, "cache_read": 0.20},
    "gemini-3-pro": {"input": 2.00, "output": 12.00, "cache_read": 0.20},
    "gemini-3-flash": {"input": 0.50, "output": 3.00, "cache_read": 0.05},
    # Gemini 2.5 family
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00, "cache_read": 0.125},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60, "cache_read": 0.03},
    "gemini-2.5-flash-lite": {"input": 0.075, "output": 0.30, "cache_read": 0.01},
    # Gemini 2.0 family
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40, "cache_read": 0.025},
    "gemini-2.0-flash-lite": {"input": 0.075, "output": 0.30, "cache_read": 0.01},
    # Gemini 1.5 family
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00, "cache_read": 0.3125},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30, "cache_read": 0.01875},
}
