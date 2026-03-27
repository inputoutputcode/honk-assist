"""OpenClaw LLM Bridge for Pipecat.

Replaces direct AnthropicLLMService with an OpenClaw agent that has
persistent memory, wake word filtering, and business context.

Uses OpenClaw's OpenAI-compatible /v1/chat/completions endpoint,
so we can reuse Pipecat's OpenAILLMService with a custom base_url.

The wake word filter ("Honk") is applied at the transcript level:
only utterances containing the wake word trigger an LLM response.
"""

import os
import re
from typing import Optional

import httpx
from loguru import logger
from openai import AsyncOpenAI, DefaultAsyncHttpxClient
from pipecat.services.openai.llm import OpenAILLMService


# Default wake word — the bot's name in meetings
WAKE_WORD = os.getenv("HONK_WAKE_WORD", "Honk")
WAKE_WORD_PATTERN = re.compile(
    rf"\b{re.escape(WAKE_WORD)}\b",
    re.IGNORECASE,
)


class OpenClawLLMService(OpenAILLMService):
    """Pipecat LLM service that routes through OpenClaw's Chat Completions API.

    This gives the meeting bot access to:
    - Persistent memory (MEMORY.md, daily files, meeting transcripts)
    - Business context (clients, projects)
    - Unified personality via SOUL.md
    - Wake word filtering (only respond when "Honk" is mentioned)

    Configuration via environment variables:
        OPENCLAW_GATEWAY_URL:   Gateway base URL (default: http://127.0.0.1:18789)
        OPENCLAW_GATEWAY_TOKEN: Gateway auth token
        OPENCLAW_AGENT_ID:      Agent to target (default: honkassist)
        HONK_WAKE_WORD:         Wake word (default: Honk)
        HONK_WAKE_WORD_ENABLED: Enable wake word filter (default: true)
    """

    def __init__(
        self,
        *,
        gateway_url: Optional[str] = None,
        gateway_token: Optional[str] = None,
        agent_id: Optional[str] = None,
        wake_word_enabled: bool = True,
        **kwargs,
    ):
        self._gateway_url = gateway_url or os.getenv(
            "OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789"
        )
        self._gateway_token = gateway_token or os.getenv("OPENCLAW_GATEWAY_TOKEN", "")
        self._agent_id = agent_id or os.getenv("OPENCLAW_AGENT_ID", "honkassist")
        self._wake_word_enabled = wake_word_enabled and os.getenv(
            "HONK_WAKE_WORD_ENABLED", "true"
        ).lower() in ("true", "1", "yes")

        base_url = f"{self._gateway_url}/v1"

        logger.info(
            f"[OPENCLAW-LLM] Initializing bridge: "
            f"gateway={self._gateway_url} agent={self._agent_id} "
            f"wake_word={'enabled' if self._wake_word_enabled else 'disabled'} "
            f"word='{WAKE_WORD}'"
        )

        # Use the OpenClaw agent id as the "model" — OpenClaw routes via
        # the model field: "openclaw:<agentId>"
        super().__init__(
            model=f"openclaw:{self._agent_id}",
            api_key=self._gateway_token,
            base_url=base_url,
            **kwargs,
        )

    def create_client(self, api_key=None, base_url=None, **kwargs):
        """Override to disable SSL verification for self-signed gateway certs."""
        return AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=DefaultAsyncHttpxClient(
                verify=False,  # OpenClaw gateway uses self-signed TLS
                limits=httpx.Limits(
                    max_keepalive_connections=100,
                    max_connections=1000,
                    keepalive_expiry=None,
                ),
            ),
        )

    def should_respond(self, transcript: str) -> bool:
        """Check if the transcript contains the wake word.
        
        Returns True if:
        - Wake word filtering is disabled, OR
        - The transcript contains the wake word "Honk"
        """
        if not self._wake_word_enabled:
            return True
        
        contains_wake_word = bool(WAKE_WORD_PATTERN.search(transcript))
        if contains_wake_word:
            logger.info(f"[OPENCLAW-LLM] Wake word '{WAKE_WORD}' detected in: {transcript[:100]}...")
        else:
            logger.debug(f"[OPENCLAW-LLM] No wake word in: {transcript[:80]}...")
        return contains_wake_word
