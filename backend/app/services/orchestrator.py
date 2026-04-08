"""
Actor-Critic Orchestrator — AI Pipeline Service

This is the core AI orchestration service that implements the
NL2Config pipeline:

  1. ACTOR: Takes the user's NL prompt (+ CSV headers) and generates
     a Pydantic-compliant GenerationConfig JSON via the LLM.
  2. CRITIC: Reviews the Actor's output for logical conflicts,
     ratio sum errors, and data type mismatches.
  3. RETRY: If the Critic finds issues, its feedback is appended
     to the prompt and the Actor is re-invoked (up to MAX_RETRIES).
  4. FALLBACK: If retries exhaust, the last draft is returned with
     requires_manual_review=True.

All LLM calls go through the abstract llm_client, so swapping
from OpenAI to Gemini is a config change, not a code change.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from app.config import settings
from app.schemas.config import GenerationConfig, DraftConfigResponse
from app.services.llm_client import invoke_llm_json
from app.services.prompts import (
    ACTOR_SYSTEM_PROMPT,
    CRITIC_SYSTEM_PROMPT,
    build_actor_prompt,
    build_critic_prompt,
    build_actor_retry_prompt,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────


async def generate_config_with_actor_critic(
    user_prompt: str,
    csv_headers: list[dict[str, str]] | None = None,
    total_records: int = 1000,
) -> DraftConfigResponse:
    """
    Execute the full Actor-Critic pipeline to generate a configuration.

    Args:
        user_prompt: The user's natural language description.
        csv_headers: Optional list of {"column_name": str, "inferred_type": str}
                     from an uploaded CSV file.
        total_records: Default record count to suggest to the Actor.

    Returns:
        DraftConfigResponse with the generated config and review metadata.
    """
    max_retries = settings.max_retries
    last_config_dict: dict[str, Any] | None = None
    last_critic_feedback: str | None = None
    iteration = 0

    for attempt in range(1, max_retries + 2):  # +1 for initial + retries
        iteration = attempt
        logger.info(f"Actor-Critic iteration {attempt}/{max_retries + 1}")

        # ── Step 1: ACTOR ─────────────────────────
        try:
            if attempt == 1:
                # First attempt: fresh prompt
                actor_user_prompt = build_actor_prompt(
                    user_prompt=user_prompt,
                    csv_headers=csv_headers,
                )
                # Add total_records hint
                actor_user_prompt += (
                    f"\n\nNote: The user wants approximately {total_records} records. "
                    f"Set total_records to {total_records}."
                )
            else:
                # Retry: include Critic feedback
                actor_user_prompt = build_actor_retry_prompt(
                    original_user_prompt=user_prompt,
                    previous_config_json=json.dumps(last_config_dict, indent=2),
                    critic_feedback_json=last_critic_feedback or "{}",
                    csv_headers=csv_headers,
                )

            logger.info(f"Invoking Actor LLM (attempt {attempt})...")
            actor_response = await invoke_llm_json(
                system_prompt=ACTOR_SYSTEM_PROMPT,
                user_prompt=actor_user_prompt,
            )
            last_config_dict = actor_response
            logger.info("Actor LLM responded with JSON config")

        except json.JSONDecodeError as e:
            logger.error(f"Actor returned invalid JSON: {e}")
            if attempt <= max_retries:
                last_critic_feedback = json.dumps({
                    "is_valid": False,
                    "issues": [{
                        "severity": "ERROR",
                        "field": "root",
                        "message": f"Your response was not valid JSON: {str(e)}. Return ONLY a JSON object."
                    }],
                    "suggestions": []
                })
                continue
            else:
                # Final attempt also failed — return error
                raise ValueError(
                    f"Actor LLM failed to produce valid JSON after {max_retries + 1} attempts"
                )

        except Exception as e:
            logger.error(f"Actor LLM call failed: {e}")
            raise

        # ── Step 1b: Pydantic Validation of Actor Output ──
        config: GenerationConfig | None = None
        pydantic_error: str | None = None

        try:
            config = GenerationConfig(**actor_response)
            logger.info("Actor output passed Pydantic validation")
        except ValidationError as e:
            pydantic_error = str(e)
            logger.warning(f"Actor output failed Pydantic validation: {pydantic_error}")

            if attempt <= max_retries:
                # Treat Pydantic errors as Critic feedback for retry
                last_critic_feedback = json.dumps({
                    "is_valid": False,
                    "issues": [{
                        "severity": "ERROR",
                        "field": "pydantic_validation",
                        "message": f"Schema validation failed: {pydantic_error}"
                    }],
                    "suggestions": [
                        "Ensure all column references exist in schema_definition",
                        "Ensure all ratios sum to exactly 100",
                        "Use only valid data_type and operator values"
                    ]
                })
                continue
            else:
                # Graceful degradation: try to fix and return with warning
                return _graceful_degradation(
                    config_dict=actor_response,
                    critic_feedback=f"Pydantic validation error: {pydantic_error}",
                    iterations=iteration,
                )

        # ── Step 2: CRITIC ────────────────────────
        try:
            logger.info(f"Invoking Critic LLM (attempt {attempt})...")
            critic_prompt = build_critic_prompt(
                json.dumps(actor_response, indent=2)
            )
            critic_response = await invoke_llm_json(
                system_prompt=CRITIC_SYSTEM_PROMPT,
                user_prompt=critic_prompt,
            )
            logger.info(f"Critic responded: is_valid={critic_response.get('is_valid')}")

        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Critic LLM failed: {e}. Accepting Actor output as-is.")
            # If Critic fails, accept the Actor's output (it passed Pydantic)
            return DraftConfigResponse(
                config=config,
                requires_manual_review=True,
                critic_feedback=f"Critic evaluation failed: {str(e)}. Please review manually.",
                actor_critic_iterations=iteration,
            )

        # ── Step 2b: Process Critic Verdict ───────
        is_valid = critic_response.get("is_valid", False)
        issues = critic_response.get("issues", [])
        errors = [i for i in issues if i.get("severity") == "ERROR"]

        if is_valid or len(errors) == 0:
            # Critic approved — return the config
            logger.info("Critic approved the configuration!")
            warnings = [i for i in issues if i.get("severity") == "WARNING"]
            feedback = None
            if warnings:
                feedback = "Warnings: " + "; ".join(
                    w.get("message", "") for w in warnings
                )

            return DraftConfigResponse(
                config=config,
                requires_manual_review=False,
                critic_feedback=feedback,
                actor_critic_iterations=iteration,
            )

        # Critic rejected — prepare for retry
        last_critic_feedback = json.dumps(critic_response, indent=2)
        logger.warning(
            f"Critic found {len(errors)} error(s). "
            f"{'Retrying...' if attempt <= max_retries else 'Max retries reached.'}"
        )

        if attempt > max_retries:
            # Max retries exhausted — graceful degradation
            return DraftConfigResponse(
                config=config,
                requires_manual_review=True,
                critic_feedback=(
                    f"Actor-Critic could not resolve all issues after "
                    f"{max_retries + 1} attempts. Last critic feedback: "
                    + "; ".join(e.get("message", "") for e in errors)
                ),
                actor_critic_iterations=iteration,
            )

    # Should never reach here, but safety net
    return _graceful_degradation(
        config_dict=last_config_dict or {},
        critic_feedback="Unexpected pipeline exit",
        iterations=iteration,
    )


# ──────────────────────────────────────────────
# Private Helpers
# ──────────────────────────────────────────────


def _graceful_degradation(
    config_dict: dict[str, Any],
    critic_feedback: str,
    iterations: int,
) -> DraftConfigResponse:
    """
    Last-resort fallback: try to construct a GenerationConfig from
    the Actor's raw output, fixing what we can. If even that fails,
    return a minimal placeholder config.
    """
    logger.warning(f"Graceful degradation triggered: {critic_feedback}")

    try:
        # Try to parse as-is
        config = GenerationConfig(**config_dict)
    except (ValidationError, Exception) as e:
        logger.error(f"Graceful degradation: cannot parse config: {e}")
        # Build a minimal fallback config
        from app.schemas.config import ColumnDefinition
        config = GenerationConfig(
            schema_definition=[
                ColumnDefinition(
                    column_name="id",
                    data_type="INT",
                    description="Placeholder — AI config generation failed",
                )
            ],
            total_records=config_dict.get("total_records", 100),
        )

    return DraftConfigResponse(
        config=config,
        requires_manual_review=True,
        critic_feedback=critic_feedback,
        actor_critic_iterations=iterations,
    )
