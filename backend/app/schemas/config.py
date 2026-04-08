"""
Core Configuration Schemas — Pydantic Data Contracts

These schemas define the strict contract between the AI orchestration
layer and the deterministic data engine. The LLM must produce output
conforming exactly to GenerationConfig. The Pandas engine consumes
GenerationConfig without any ambiguity.

Key design decisions:
  - All constraints are mathematically precise (ratios sum to 100).
  - Boundary operators are limited to a strict enum.
  - Data types map directly to Pandas/NumPy dtypes.
  - config_id is auto-generated if not provided, used for seeding.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ──────────────────────────────────────────────
# Enums — Strict value sets
# ──────────────────────────────────────────────


class DataType(str, Enum):
    """Allowed data types for schema columns.
    Maps directly to generation strategies in the Pandas engine."""
    INT = "INT"
    FLOAT = "FLOAT"
    STRING = "STRING"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    DATETIME = "DATETIME"
    UUID = "UUID"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    NAME = "NAME"
    ADDRESS = "ADDRESS"


class BoundaryOperator(str, Enum):
    """Operators for boundary/edge-case rules."""
    GT = ">"
    LT = "<"
    GTE = ">="
    LTE = "<="
    EQ = "="
    NEQ = "!="
    BETWEEN = "BETWEEN"


# ──────────────────────────────────────────────
# Schema Building Blocks
# ──────────────────────────────────────────────


class ColumnDefinition(BaseModel):
    """
    Defines a single column in the synthetic dataset.

    Attributes:
        column_name: The exact column header name.
        data_type: The data type (INT, STRING, BOOLEAN, etc.).
        nullable: Whether this column can contain null values.
        description: Optional human-readable description of the column.
    """
    column_name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Column header name",
        examples=["credit_score", "applicant_name", "loan_amount"],
    )
    data_type: DataType = Field(
        ...,
        description="Data type for this column",
        examples=["INT", "STRING", "BOOLEAN"],
    )
    nullable: bool = Field(
        default=False,
        description="Whether null values are allowed",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Human-readable column description",
    )

    class Config:
        use_enum_values = True


class DistributionConstraint(BaseModel):
    """
    Defines a categorical distribution for a column.

    The categories and ratios must have the same length,
    and ratios must sum to exactly 100.

    Example:
        column_name: "risk_tier"
        categories: ["Prime", "Sub-prime", "Near-prime"]
        ratios: [50, 30, 20]
    """
    column_name: str = Field(
        ...,
        min_length=1,
        description="Column to apply distribution constraint on",
    )
    categories: list[str] = Field(
        ...,
        min_length=1,
        description="List of categorical values",
        examples=[["Prime", "Sub-prime", "Near-prime"]],
    )
    ratios: list[int] = Field(
        ...,
        min_length=1,
        description="Distribution percentages — must sum to 100",
        examples=[[50, 30, 20]],
    )

    @field_validator("categories", mode="before")
    @classmethod
    def stringify_categories(cls, v: list[Any]) -> list[str]:
        """Coerce all category values to strings to satisfy Pydantic typing."""
        if isinstance(v, list):
            return [str(item) for item in v]
        return v

    @field_validator("ratios")
    @classmethod
    def ratios_must_sum_to_100(cls, v: list[int]) -> list[int]:
        """Enforce that distribution ratios sum to exactly 100."""
        total = sum(v)
        if total != 100:
            raise ValueError(
                f"Distribution ratios must sum to 100, got {total}. "
                f"Ratios provided: {v}"
            )
        if any(r < 0 for r in v):
            raise ValueError(
                f"All ratios must be non-negative. Got: {v}"
            )
        return v

    @model_validator(mode="after")
    def categories_ratios_length_match(self) -> "DistributionConstraint":
        """Ensure categories and ratios lists have the same length."""
        if len(self.categories) != len(self.ratios):
            raise ValueError(
                f"categories ({len(self.categories)} items) and "
                f"ratios ({len(self.ratios)} items) must have the same length."
            )
        return self


class BoundaryRule(BaseModel):
    """
    Defines an edge-case boundary rule for testing.

    The engine will inject rows that test the exact boundary
    (e.g., for score > 700: inject rows with scores 699, 700, 701).

    Attributes:
        column_name: Column to apply the boundary rule on.
        operator: Comparison operator (>, <, =, BETWEEN, etc.).
        value: The boundary value(s). Single value or [low, high] for BETWEEN.
        action: The expected decisioning outcome (e.g., "approve", "reject").
        description: Optional human-readable description of the rule.
    """
    column_name: str = Field(
        ...,
        min_length=1,
        description="Column to apply boundary rule on",
    )
    operator: BoundaryOperator = Field(
        ...,
        description="Comparison operator",
        examples=[">", "<", "=", "BETWEEN"],
    )
    value: Any = Field(
        ...,
        description=(
            "Boundary threshold value. Single number/string for most operators, "
            "or a list of [low, high] for BETWEEN."
        ),
        examples=[700, [600, 750]],
    )
    action: str = Field(
        ...,
        min_length=1,
        description="Expected decisioning outcome for this boundary",
        examples=["approve", "reject", "manual_review"],
    )
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Human-readable description of this boundary rule",
    )

    @model_validator(mode="after")
    def validate_between_has_two_values(self) -> "BoundaryRule":
        """BETWEEN operator requires exactly [low, high] pair."""
        if self.operator == BoundaryOperator.BETWEEN:
            if not isinstance(self.value, list) or len(self.value) != 2:
                raise ValueError(
                    "BETWEEN operator requires value to be a list of "
                    f"[low, high]. Got: {self.value}"
                )
        return self

    class Config:
        use_enum_values = True


class InterdependentRule(BaseModel):
    """
    Defines a conditional logic rule to populate a column based on another column's value.
    
    Example: 
        If condition_column ('risk_tier') condition_operator ('=') condition_value ('Sub-prime'),
        then populate target_column ('credit_score') with target_fill_value ([300, 500]).
    """
    target_column: str = Field(
        ...,
        min_length=1,
        description="The column to populate based on the condition",
    )
    condition_column: str = Field(
        ...,
        min_length=1,
        description="The anchor column to check the logic against",
    )
    condition_operator: BoundaryOperator = Field(
        ...,
        description="Comparison operator for the condition",
        examples=["=", ">", "<", "BETWEEN"],
    )
    condition_value: Any = Field(
        ...,
        description="Value to evaluate against the condition_column",
    )
    target_fill_value: Any = Field(
        ...,
        description="Value or range [low, high] to explicitly overwrite the target_column with",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Human-readable description of this logic rule",
    )
    
    @model_validator(mode="after")
    def validate_between_has_two_values(self) -> "InterdependentRule":
        """BETWEEN operator requires exactly [low, high] pair in condition_value."""
        if self.condition_operator == BoundaryOperator.BETWEEN:
            if not isinstance(self.condition_value, list) or len(self.condition_value) != 2:
                raise ValueError(
                    "BETWEEN condition operator requires condition_value to be a list of "
                    f"[low, high]. Got: {self.condition_value}"
                )
        return self

    class Config:
        use_enum_values = True


# ──────────────────────────────────────────────
# Top-Level Configuration
# ──────────────────────────────────────────────


class GenerationConfig(BaseModel):
    """
    The complete configuration contract for synthetic data generation.

    This is the core data structure that flows through the entire pipeline:
      1. The Actor LLM produces this from a natural language prompt.
      2. The Critic LLM validates this for logical consistency.
      3. The React UI displays and allows editing of this.
      4. The Pandas engine consumes this to generate deterministic data.

    The config_id serves double duty:
      - Unique identifier for the configuration.
      - Seed source (hashed) for np.random and Faker determinism.
    """
    config_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique config identifier — also used as deterministic seed source",
    )
    schema_definition: list[ColumnDefinition] = Field(
        ...,
        min_length=1,
        description="List of column definitions for the synthetic dataset",
    )
    distribution_constraints: list[DistributionConstraint] = Field(
        default_factory=list,
        description="Categorical distribution rules (column → categories + ratios)",
    )
    boundary_rules: list[BoundaryRule] = Field(
        default_factory=list,
        description="Edge-case boundary rules for testing decisioning logic",
    )
    interdependent_rules: list[InterdependentRule] = Field(
        default_factory=list,
        description="Conditional logic rules for filling interdependent columns",
    )
    total_records: int = Field(
        ...,
        gt=0,
        le=10_000_000,
        description="Total number of rows to generate (max 10 million)",
        examples=[1000, 100_000, 1_000_000],
    )

    @model_validator(mode="after")
    def validate_column_references(self) -> "GenerationConfig":
        """
        Ensure all column_name references in constraints and rules
        actually exist in the schema_definition.
        """
        defined_columns = {col.column_name for col in self.schema_definition}

        # Check distribution constraints
        for dc in self.distribution_constraints:
            if dc.column_name not in defined_columns:
                raise ValueError(
                    f"Distribution constraint references column '{dc.column_name}' "
                    f"which is not defined in schema_definition. "
                    f"Available columns: {defined_columns}"
                )

        # Check boundary rules
        for br in self.boundary_rules:
            if br.column_name not in defined_columns:
                raise ValueError(
                    f"Boundary rule references column '{br.column_name}' "
                    f"which is not defined in schema_definition. "
                    f"Available columns: {defined_columns}"
                )

        # Check interdependent rules
        for ir in self.interdependent_rules:
            if ir.target_column not in defined_columns:
                raise ValueError(
                    f"Interdependent rule target '{ir.target_column}' "
                    f"is not defined in schema_definition."
                )
            if ir.condition_column not in defined_columns:
                raise ValueError(
                    f"Interdependent rule condition '{ir.condition_column}' "
                    f"is not defined in schema_definition."
                )

        return self


# ──────────────────────────────────────────────
# API Response Models
# ──────────────────────────────────────────────


class DraftConfigResponse(BaseModel):
    """
    Response from the Actor-Critic AI pipeline.

    Contains the generated configuration plus metadata about
    whether the Critic fully approved it or flagged it for manual review.
    """
    config: GenerationConfig = Field(
        ...,
        description="The generated configuration",
    )
    requires_manual_review: bool = Field(
        default=False,
        description=(
            "If True, the Critic could not resolve all logical conflicts "
            "within the retry limit. The user should review carefully."
        ),
    )
    critic_feedback: Optional[str] = Field(
        default=None,
        description="Last critic feedback message, if any issues were found",
    )
    actor_critic_iterations: int = Field(
        default=1,
        ge=1,
        description="Number of Actor-Critic iterations executed",
    )
