"""Wrap the asynchronous OpenAI client for ticket-event verification questions.

A shared system prompt requests a short answer. Response text is returned
unchanged for the caller to enter into the page.
"""
from openai import AsyncOpenAI
from src.model.llm import LLMConfig

SYSTEM_PROMPT = """
Ticket event QA assistant.

Rules:
- Answer only.
- No explanation.
- Multiple choice → return only A/B/C/D.
- If unknown → return UNKNOWN.
"""

class ChatgptClient:
    """Answer verification questions through the configured asynchronous model client."""
    def __init__(self, config: LLMConfig):
        """Create an asynchronous API client using the supplied model configuration."""
        self.config = config
        self.client = AsyncOpenAI(api_key=self.config.api_key)

    async def chat(self, messages):
        """Submit messages after the shared system prompt and return raw output text."""
        response = await self.client.responses.create(
            model=self.config.model_name,
            input=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                *messages
            ]
        )

        return response.output_text
