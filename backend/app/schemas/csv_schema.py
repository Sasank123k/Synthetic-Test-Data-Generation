"""
CSV Schema Extraction — Request/Response Models

Used by the POST /api/extract-schema endpoint to parse
uploaded CSV files and return inferred column headers + types.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class InferredColumn(BaseModel):
    """A single column inferred from a CSV file."""
    column_name: str = Field(
        ...,
        description="Exact column header from the CSV",
    )
    inferred_type: str = Field(
        ...,
        description="Pandas-inferred dtype (e.g., 'int64', 'object', 'float64')",
    )
    suggested_data_type: str = Field(
        ...,
        description=(
            "Mapped suggestion for our DataType enum "
            "(INT, FLOAT, STRING, BOOLEAN, DATE, etc.)"
        ),
    )
    sample_values: list[str] = Field(
        default_factory=list,
        description="Up to 5 sample values from the CSV for reference",
    )
    null_count: int = Field(
        default=0,
        description="Number of null/NaN values found in the sampled rows",
    )


class CSVSchemaResponse(BaseModel):
    """Response from CSV schema extraction."""
    filename: str = Field(
        ...,
        description="Name of the uploaded file",
    )
    total_columns: int = Field(
        ...,
        description="Number of columns detected",
    )
    rows_sampled: int = Field(
        ...,
        description="Number of rows read for type inference",
    )
    columns: list[InferredColumn] = Field(
        ...,
        description="List of inferred column definitions",
    )
