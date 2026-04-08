"""
Pydantic schemas for the Synthetic Data Engine.

All data contracts are exported from this package for convenient imports:
    from app.schemas import GenerationConfig, DraftConfigResponse, ...
"""

from app.schemas.config import (
    DataType,
    BoundaryOperator,
    ColumnDefinition,
    DistributionConstraint,
    BoundaryRule,
    GenerationConfig,
    DraftConfigResponse,
)
from app.schemas.csv_schema import (
    InferredColumn,
    CSVSchemaResponse,
)
from app.schemas.generation import (
    JobStatus,
    GenerationRequest,
    GenerationJobResponse,
    GenerationProgress,
    DistributionCheck,
    BoundaryCheck,
    ValidationResult,
)

__all__ = [
    # Config
    "DataType",
    "BoundaryOperator",
    "ColumnDefinition",
    "DistributionConstraint",
    "BoundaryRule",
    "GenerationConfig",
    "DraftConfigResponse",
    # CSV
    "InferredColumn",
    "CSVSchemaResponse",
    # Generation
    "JobStatus",
    "GenerationRequest",
    "GenerationJobResponse",
    "GenerationProgress",
    "DistributionCheck",
    "BoundaryCheck",
    "ValidationResult",
]
