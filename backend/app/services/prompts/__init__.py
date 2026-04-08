"""
Version-controlled system prompts for the Actor-Critic LLM pipeline.

Actor: Translates natural language → strict JSON configuration.
Critic: Validates the Actor's output for logical conflicts.
"""

from app.services.prompts.actor_prompt import (
    ACTOR_SYSTEM_PROMPT,
    ACTOR_SYSTEM_PROMPT_VERSION,
    build_actor_prompt,
)
from app.services.prompts.critic_prompt import (
    CRITIC_SYSTEM_PROMPT,
    CRITIC_SYSTEM_PROMPT_VERSION,
    build_critic_prompt,
    build_actor_retry_prompt,
)

__all__ = [
    "ACTOR_SYSTEM_PROMPT",
    "ACTOR_SYSTEM_PROMPT_VERSION",
    "build_actor_prompt",
    "CRITIC_SYSTEM_PROMPT",
    "CRITIC_SYSTEM_PROMPT_VERSION",
    "build_critic_prompt",
    "build_actor_retry_prompt",
]
