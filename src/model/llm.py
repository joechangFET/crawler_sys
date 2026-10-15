"""Declare configuration defaults for the language-model client."""
from dataclasses import dataclass

@dataclass
class LLMConfig:
    """Store the API key and model defaults used by ChatgptClient."""
    api_key: str
    model_name: str = "gpt-5-mini"
    temperature: float = 0.1
