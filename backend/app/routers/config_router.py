"""
Config Router — AI Orchestration Endpoint

Endpoint: POST /api/generate-draft-config
Accepts a natural language prompt (+ optional CSV file) and returns
a drafted GenerationConfig via the Actor-Critic LLM chain.

The flow:
  1. If CSV is uploaded, extract headers + types (first 5 rows).
  2. Invoke the Actor-Critic orchestrator pipeline.
  3. Return DraftConfigResponse with the generated config + review metadata.
"""

from __future__ import annotations

import io
import logging
from typing import Optional

import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.schemas.config import DraftConfigResponse
from app.routers.csv_router import _map_dtype
from app.services.orchestrator import generate_config_with_actor_critic

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Configuration"])


# ──────────────────────────────────────────────
# POST /api/generate-draft-config
# ──────────────────────────────────────────────


@router.post(
    "/generate-draft-config",
    response_model=DraftConfigResponse,
    summary="Generate draft configuration from natural language",
    description=(
        "Submit a natural language prompt describing the test scenario. "
        "Optionally upload a CSV file to extract column headers as ground truth. "
        "The Actor-Critic LLM chain generates a strictly typed JSON configuration "
        "for human review and approval.\n\n"
        "**Flow:**\n"
        "1. CSV headers extracted (if file provided)\n"
        "2. Actor LLM drafts a JSON config from prompt + headers\n"
        "3. Critic LLM validates for logical conflicts\n"
        "4. Retry loop if Critic rejects (up to MAX_RETRIES)\n"
        "5. Graceful degradation if retries exhaust"
    ),
)
async def generate_draft_config(
    prompt: str = Form(
        ...,
        description="Natural language description of the test scenario",
        examples=["Generate credit scoring data with 60% prime, 25% near-prime, and 15% sub-prime borrowers"],
    ),
    csv_file: Optional[UploadFile] = File(
        default=None,
        description="Optional CSV file to extract column headers from",
    ),
    total_records: int = Form(
        default=1000,
        description="Desired number of records",
    ),
) -> DraftConfigResponse:
    """
    Generate a draft configuration using the Actor-Critic LLM chain.

    If a CSV file is provided, its headers are extracted and used as
    ground-truth column names to prevent the Actor from hallucinating
    non-existent fields.
    """
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    # ── Extract CSV headers (if file provided) ──
    csv_headers: list[dict[str, str]] | None = None

    if csv_file is not None:
        if not csv_file.filename or not csv_file.filename.lower().endswith(".csv"):
            raise HTTPException(
                status_code=400,
                detail=f"Only CSV files are supported. Got: {csv_file.filename}",
            )

        try:
            content = await csv_file.read()
            if not content:
                raise HTTPException(status_code=400, detail="CSV file is empty")

            df = pd.read_csv(
                io.BytesIO(content),
                nrows=5,  # Read only first 5 rows for efficiency
                encoding="utf-8",
                encoding_errors="replace",
            )

            csv_headers = [
                {
                    "column_name": str(col),
                    "inferred_type": _map_dtype(df[col].dtype),
                }
                for col in df.columns
            ]
            logger.info(
                f"Extracted {len(csv_headers)} columns from CSV: "
                f"{[h['column_name'] for h in csv_headers]}"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"CSV parsing failed, proceeding without headers: {e}")
            csv_headers = None

    # ── Run Actor-Critic Pipeline ──────────────
    try:
        result = await generate_config_with_actor_critic(
            user_prompt=prompt,
            csv_headers=csv_headers,
            total_records=total_records,
        )
        logger.info(
            f"Config generated: {len(result.config.schema_definition)} columns, "
            f"{len(result.config.distribution_constraints)} distributions, "
            f"{len(result.config.boundary_rules)} boundary rules. "
            f"Manual review: {result.requires_manual_review}"
        )
        return result

    except ValueError as e:
        # Actor-Critic pipeline exhausted all retries and graceful degradation
        raise HTTPException(
            status_code=500,
            detail=f"AI configuration generation failed: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Unexpected error in AI pipeline: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=(
                "AI configuration generation encountered an unexpected error. "
                "Please check your LLM API key and try again."
            ),
        )
