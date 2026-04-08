"""
Generation Request/Response — Pydantic Models

Models for the stateless generation flow:
  1. Frontend sends the full approved config via POST /api/execute-generation
  2. Backend returns a job_id for WebSocket tracking and CSV download
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.config import GenerationConfig


class JobStatus(str, Enum):
    """Status of a generation job."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class GenerationRequest(BaseModel):
    """
    Request body for POST /api/execute-generation.

    The frontend sends the entire approved configuration in a single
    stateless request. No prior server-side storage required.
    """
    config: GenerationConfig = Field(
        ...,
        description="The fully approved generation configuration",
    )
    chunk_size: int = Field(
        default=100_000,
        gt=0,
        le=1_000_000,
        description="Number of rows per chunk for memory-efficient generation",
    )


class GenerationJobResponse(BaseModel):
    """
    Immediate response after submitting a generation request.

    The job_id is used to:
      - Connect via WebSocket for live progress (ws://host/ws/generation/{job_id})
      - Download the result via GET /api/export/{job_id}
    """
    job_id: str = Field(
        ...,
        description="Unique job identifier for tracking",
    )
    status: JobStatus = Field(
        default=JobStatus.QUEUED,
        description="Current job status",
    )
    message: str = Field(
        default="Generation job queued successfully",
        description="Human-readable status message",
    )
    total_records: int = Field(
        ...,
        description="Total records that will be generated",
    )
    total_chunks: int = Field(
        ...,
        description="Number of chunks the generation will be split into",
    )


class GenerationProgress(BaseModel):
    """
    WebSocket progress payload — streamed to the frontend
    as the Pandas engine processes each step within each chunk.
    """
    job_id: str
    status: JobStatus
    current_stage: str = Field(
        ...,
        description="Current pipeline stage",
        examples=["distribution_allocation", "boundary_injection", "interdependent_fill", "tagging", "validation"],
    )
    current_chunk: int = Field(
        ...,
        description="Current chunk being processed (1-indexed)",
    )
    total_chunks: int
    rows_processed: int = Field(
        ...,
        description="Total rows generated so far across all chunks",
    )
    total_rows: int
    progress_percent: float = Field(
        ...,
        ge=0,
        le=100,
        description="Overall progress percentage",
    )
    message: Optional[str] = Field(
        default=None,
        description="Optional status message for the current stage",
    )


class DistributionCheck(BaseModel):
    """Validation result for a single distribution constraint."""
    column_name: str
    expected_ratios: dict[str, float] = Field(
        ...,
        description="Expected category → percentage mapping",
    )
    actual_ratios: dict[str, float] = Field(
        ...,
        description="Actual category → percentage mapping from generated data",
    )
    is_pass: bool
    deviation: float = Field(
        ...,
        description="Maximum percentage-point deviation from expected",
    )


class BoundaryCheck(BaseModel):
    """Validation result for a single boundary rule."""
    column_name: str
    operator: str
    value: str
    boundary_rows_found: int = Field(
        ...,
        description="Number of rows injected to test this boundary",
    )
    is_pass: bool


class ValidationResult(BaseModel):
    """
    Post-generation validation results.

    Checks that the generated data actually matches the
    requested distribution ratios and boundary rules.
    """
    is_valid: bool = Field(
        ...,
        description="Whether all validations passed",
    )
    distribution_checks: list[DistributionCheck] = Field(
        default_factory=list,
        description="Per-column distribution accuracy results",
    )
    boundary_checks: list[BoundaryCheck] = Field(
        default_factory=list,
        description="Per-rule boundary coverage results",
    )
    total_rows_generated: int = Field(
        ...,
        description="Actual number of rows in the final dataset",
    )
