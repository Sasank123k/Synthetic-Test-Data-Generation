"""
CSV Schema Extraction Router

Endpoint: POST /api/extract-schema
Accepts a CSV file upload, reads only the first N rows for efficiency,
infers column headers and data types, and returns a structured response.

This gives the frontend (and the Actor LLM) ground-truth column headers
to prevent hallucination of non-existent fields.
"""

from __future__ import annotations

import io

import pandas as pd
from fastapi import APIRouter, File, UploadFile, HTTPException, Query

from app.schemas.csv_schema import CSVSchemaResponse, InferredColumn

router = APIRouter(prefix="/api", tags=["CSV Schema"])

# ──────────────────────────────────────────────
# Pandas dtype → our DataType enum mapping
# ──────────────────────────────────────────────

DTYPE_MAP: dict[str, str] = {
    "int64": "INT",
    "int32": "INT",
    "Int64": "INT",
    "Int32": "INT",
    "float64": "FLOAT",
    "float32": "FLOAT",
    "Float64": "FLOAT",
    "object": "STRING",
    "string": "STRING",
    "bool": "BOOLEAN",
    "boolean": "BOOLEAN",
    "datetime64[ns]": "DATETIME",
    "datetime64": "DATETIME",
    "category": "STRING",
}


def _map_dtype(pandas_dtype: str) -> str:
    """Map a Pandas dtype string to our DataType enum value."""
    dtype_str = str(pandas_dtype)
    return DTYPE_MAP.get(dtype_str, "STRING")


# ──────────────────────────────────────────────
# POST /api/extract-schema
# ──────────────────────────────────────────────


@router.post(
    "/extract-schema",
    response_model=CSVSchemaResponse,
    summary="Extract schema from CSV",
    description=(
        "Upload a CSV file to extract column headers and inferred data types. "
        "Only the first N rows are read for efficiency (default 10). "
        "Returns structured column metadata for the configuration builder."
    ),
)
async def extract_csv_schema(
    file: UploadFile = File(
        ...,
        description="CSV file to extract schema from",
    ),
    sample_rows: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Number of rows to read for type inference (default 10)",
    ),
) -> CSVSchemaResponse:
    """
    Parse an uploaded CSV and return inferred schema information.

    Optimized: reads only the first N rows to prevent memory exhaustion
    on large files. This establishes the "Source of Truth" for column
    headers that the Actor LLM must respect.
    """
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail=f"Only CSV files are supported. Got: {file.filename}",
        )

    try:
        # Read file content
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        # Parse CSV — only first N rows for performance
        df = pd.read_csv(
            io.BytesIO(content),
            nrows=sample_rows,
            encoding="utf-8",
            encoding_errors="replace",
        )

        if df.empty:
            raise HTTPException(status_code=400, detail="CSV file contains no data rows")

        if len(df.columns) == 0:
            raise HTTPException(status_code=400, detail="CSV file contains no columns")

    except pd.errors.EmptyDataError:
        raise HTTPException(status_code=400, detail="CSV file is empty or malformed")
    except pd.errors.ParserError as e:
        raise HTTPException(status_code=400, detail=f"CSV parsing error: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse CSV: {str(e)}")

    # Build column metadata
    columns: list[InferredColumn] = []
    for col_name in df.columns:
        col_series = df[col_name]

        # Get sample values (up to 5 unique non-null values)
        non_null = col_series.dropna()
        sample_values = [str(v) for v in non_null.unique()[:5]]

        columns.append(
            InferredColumn(
                column_name=str(col_name),
                inferred_type=str(col_series.dtype),
                suggested_data_type=_map_dtype(col_series.dtype),
                sample_values=sample_values,
                null_count=int(col_series.isna().sum()),
            )
        )

    return CSVSchemaResponse(
        filename=file.filename,
        total_columns=len(df.columns),
        rows_sampled=len(df),
        columns=columns,
    )
