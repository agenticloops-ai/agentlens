"""OpenAI pricing tables.

All prices are per 1M tokens in USD.
"""

OPENAI_PRICING: dict[str, dict[str, float]] = {
    # Codex
    "gpt-5.3-codex": {"input": 2.50, "output": 10.00},
    "gpt-5.3": {"input": 2.50, "output": 10.00},
    # GPT-4.1 family
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    # GPT-4o family
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    # Reasoning models
    "o4-mini": {"input": 1.10, "output": 4.40},
    "o3-mini": {"input": 1.10, "output": 4.40},
    "o3": {"input": 2.00, "output": 8.00},
    "o1-mini": {"input": 3.00, "output": 12.00},
    "o1": {"input": 15.00, "output": 60.00},
    # Legacy
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
}
