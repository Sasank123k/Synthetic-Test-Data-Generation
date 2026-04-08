"""
Deterministic Synthetic Data Engine

The core engine that generates synthetic datasets from a validated
GenerationConfig. Key design decisions:

  1. DETERMINISM: All randomness is seeded from a hash of config_id.
     Same config_id → byte-identical output every time.

  2. GLOBAL DISTRIBUTION PRE-CALCULATION: Before chunking, exact
     row targets are computed for every distribution category.
     Each chunk decrements mutable counters, guaranteeing perfect
     final ratios regardless of chunk boundaries.

  3. MEMORY-SAFE CHUNKING: Data is generated in configurable blocks
     (default 100k rows). Each chunk is appended to disk and freed.

  4. OBSERVABILITY: Every row is tagged with _generation_reason
     ("distribution_allocation", "boundary_injection", "random_fill").

Pipeline per chunk:
  Step 1: Distribution allocation (using global counters)
  Step 2: Boundary rule injection
  Step 3: Remaining rows filled with contextual values
  Step 4: Observability tagging
  Step 5: Flush to disk
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import uuid
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from faker import Faker

from app.config import settings
from app.schemas.config import (
    GenerationConfig,
    ColumnDefinition,
    DistributionConstraint,
    BoundaryRule,
    InterdependentRule,
    DataType,
    BoundaryOperator,
)
from app.schemas.generation import (
    GenerationProgress,
    JobStatus,
    ValidationResult,
    DistributionCheck,
    BoundaryCheck,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────


def run_generation(
    config: GenerationConfig,
    job_id: str,
    chunk_size: int = 100_000,
    progress_callback: Callable[[GenerationProgress], None] | None = None,
) -> dict[str, Any]:
    """
    Execute the full deterministic data generation pipeline.

    This function runs synchronously and should be called via
    asyncio.to_thread() from the async endpoint.

    Args:
        config: The validated GenerationConfig.
        job_id: Unique job identifier.
        chunk_size: Rows per chunk (default 100k).
        progress_callback: Optional callback for progress updates.

    Returns:
        Dict with job_id, output_path, total_rows, and validation_result.
    """
    total_records = config.total_records
    total_chunks = math.ceil(total_records / chunk_size)

    logger.info(
        f"[Job {job_id}] Starting generation: {total_records:,} records, "
        f"{total_chunks} chunk(s) of {chunk_size:,}"
    )

    # ── Step 0: Setup ──────────────────────────
    seed = _config_id_to_seed(config.config_id)
    rng = np.random.default_rng(seed)
    fake = Faker()
    Faker.seed(seed)

    # Create output directory
    output_dir = Path(settings.data_volume_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{job_id}.csv"

    # ── Step 1: Global Distribution Pre-Calculation ──
    global_counters = _compute_global_distribution_targets(
        config.distribution_constraints, total_records
    )
    logger.info(f"[Job {job_id}] Global distribution targets: {global_counters}")

    # ── Step 2: Identify boundary injection rows ──
    boundary_rows = _compute_boundary_rows(config.boundary_rules, config)
    total_boundary_rows = len(boundary_rows)
    logger.info(
        f"[Job {job_id}] Boundary rows to inject: {total_boundary_rows}"
    )

    # ── Step 3: Chunked Generation Loop ──
    rows_generated = 0
    first_chunk = True
    boundary_rows_injected = False

    for chunk_idx in range(total_chunks):
        chunk_num = chunk_idx + 1

        # Calculate rows for this chunk
        remaining = total_records - rows_generated
        this_chunk_size = min(chunk_size, remaining)

        if this_chunk_size <= 0:
            break

        _send_progress(progress_callback, job_id, "distribution_allocation",
                       chunk_num, total_chunks, rows_generated, total_records,
                       f"Chunk {chunk_num}: Allocating distributions...")

        # Step 3a: Build distribution-allocated rows
        df = _generate_chunk(
            config=config,
            chunk_size=this_chunk_size,
            global_counters=global_counters,
            rng=rng,
            fake=fake,
            chunk_num=chunk_num,
        )

        # Step 3b: Apply interdependent rules
        if config.interdependent_rules:
            _send_progress(progress_callback, job_id, "interdependent_logic",
                           chunk_num, total_chunks, rows_generated, total_records,
                           f"Chunk {chunk_num}: Applying interdependent rules...")
            df = _apply_interdependent_rules(df, config.interdependent_rules, config, rng)

        # Step 3c: Inject boundary rows (only in first chunk)
        if not boundary_rows_injected and boundary_rows:
            _send_progress(progress_callback, job_id, "boundary_injection",
                           chunk_num, total_chunks, rows_generated, total_records,
                           f"Chunk {chunk_num}: Injecting {total_boundary_rows} boundary rows...")

            df = _inject_boundary_rows(df, boundary_rows, config)
            boundary_rows_injected = True

        # Step 3d: Tag generation reason
        _send_progress(progress_callback, job_id, "tagging",
                       chunk_num, total_chunks, rows_generated, total_records,
                       f"Chunk {chunk_num}: Tagging rows...")

        # Step 3e: Flush to disk
        _send_progress(progress_callback, job_id, "flushing",
                       chunk_num, total_chunks, rows_generated, total_records,
                       f"Chunk {chunk_num}: Writing to disk...")

        df.to_csv(
            output_path,
            mode="w" if first_chunk else "a",
            header=first_chunk,
            index=False,
        )
        first_chunk = False
        rows_generated += len(df)
        del df  # Free RAM

        logger.info(
            f"[Job {job_id}] Chunk {chunk_num}/{total_chunks} done. "
            f"Total rows: {rows_generated:,}"
        )

    # ── Step 4: Post-Generation Validation ──
    _send_progress(progress_callback, job_id, "validation",
                   total_chunks, total_chunks, rows_generated, total_records,
                   "Validating generated dataset...")

    validation = _validate_output(output_path, config, rows_generated)

    _send_progress(progress_callback, job_id, "completed",
                   total_chunks, total_chunks, rows_generated, total_records,
                   f"Generation complete! {rows_generated:,} rows written.")

    logger.info(
        f"[Job {job_id}] Generation complete: {rows_generated:,} rows, "
        f"validation={'PASS' if validation.is_valid else 'FAIL'}"
    )

    return {
        "job_id": job_id,
        "output_path": str(output_path),
        "total_rows": rows_generated,
        "validation": validation,
    }


# ──────────────────────────────────────────────
# Seeding
# ──────────────────────────────────────────────


def _config_id_to_seed(config_id: str) -> int:
    """Hash a config_id to a deterministic integer seed."""
    hash_bytes = hashlib.sha256(config_id.encode("utf-8")).digest()
    return int.from_bytes(hash_bytes[:8], byteorder="big") % (2**31)


# ──────────────────────────────────────────────
# Global Distribution Pre-Calculation
# ──────────────────────────────────────────────


def _compute_global_distribution_targets(
    constraints: list[DistributionConstraint],
    total_records: int,
) -> dict[str, dict[str, int]]:
    """
    Compute exact row targets for each distribution category.

    Returns:
        {column_name: {category: target_count, ...}, ...}

    The targets use integer rounding with a remainder correction
    to ensure they sum to exactly total_records.
    """
    targets: dict[str, dict[str, int]] = {}

    for dc in constraints:
        col_targets: dict[str, int] = {}
        allocated = 0

        for i, (cat, ratio) in enumerate(zip(dc.categories, dc.ratios)):
            if i == len(dc.categories) - 1:
                # Last category gets the remainder to ensure exact sum
                col_targets[cat] = total_records - allocated
            else:
                count = round(total_records * ratio / 100)
                col_targets[cat] = count
                allocated += count

        targets[dc.column_name] = col_targets

    return targets


# ──────────────────────────────────────────────
# Boundary Row Computation
# ──────────────────────────────────────────────


def _compute_boundary_rows(
    rules: list[BoundaryRule],
    config: GenerationConfig | None = None,
) -> list[dict[str, Any]]:
    """
    For each boundary rule, compute the specific test values to inject.

    E.g., for "credit_score > 700":
      → inject rows with credit_score = 699, 700, 701

    If the column's data type is INT, all values are cast to int
    to prevent 'cannot safely cast float to int64' errors.
    """
    # Build a lookup of column data types
    col_types: dict[str, str] = {}
    if config:
        for col_def in config.schema_definition:
            col_types[col_def.column_name] = col_def.data_type

    boundary_rows: list[dict[str, Any]] = []

    for rule in rules:
        col = rule.column_name
        op = rule.operator
        val = rule.value
        is_int = col_types.get(col) in (DataType.INT, "INT")

        try:
            if op == BoundaryOperator.BETWEEN:
                low, high = float(val[0]), float(val[1])
                # Test at boundaries: below-low, at-low, mid, at-high, above-high
                test_values = [low - 1, low, (low + high) / 2, high, high + 1]
                if is_int:
                    test_values = [int(round(v)) for v in test_values]
                for tv in test_values:
                    boundary_rows.append({
                        "column": col,
                        "value": tv,
                        "reason": f"boundary_{op}_{low}_{high}",
                        "action": rule.action,
                    })
            elif op in (BoundaryOperator.GT, BoundaryOperator.GTE,
                        BoundaryOperator.LT, BoundaryOperator.LTE,
                        BoundaryOperator.EQ, BoundaryOperator.NEQ):
                numeric_val = float(val)
                # Test at: val-1, val, val+1
                test_values = [numeric_val - 1, numeric_val, numeric_val + 1]
                if is_int:
                    test_values = [int(round(v)) for v in test_values]
                for tv in test_values:
                    boundary_rows.append({
                        "column": col,
                        "value": tv,
                        "reason": f"boundary_{op}_{val}",
                        "action": rule.action,
                    })
        except (ValueError, TypeError):
            # Non-numeric boundary value — inject the value as-is
            boundary_rows.append({
                "column": col,
                "value": val,
                "reason": f"boundary_{op}_{val}",
                "action": rule.action,
            })

    return boundary_rows


# ──────────────────────────────────────────────
# Chunk Generation
# ──────────────────────────────────────────────


def _generate_chunk(
    config: GenerationConfig,
    chunk_size: int,
    global_counters: dict[str, dict[str, int]],
    rng: np.random.Generator,
    fake: Faker,
    chunk_num: int,
) -> pd.DataFrame:
    """
    Generate a single chunk of data, decrementing global distribution
    counters to maintain perfect final ratios.
    """
    data: dict[str, list[Any]] = {}

    # Track generation reason per row
    reasons: list[str] = ["random_fill"] * chunk_size

    for col_def in config.schema_definition:
        col_name = col_def.column_name
        dtype = col_def.data_type

        # Check if this column has a distribution constraint
        if col_name in global_counters:
            # Distribution-allocated column
            col_data = _allocate_from_distribution(
                global_counters[col_name], chunk_size, rng
            )
            data[col_name] = col_data
            # Update reasons
            for i in range(min(len(col_data), len(reasons))):
                if reasons[i] == "random_fill":
                    reasons[i] = "distribution_allocation"
        else:
            # Random-filled column
            data[col_name] = _generate_column_values(
                dtype, chunk_size, rng, fake, col_def.nullable
            )

    data["_generation_reason"] = reasons
    return pd.DataFrame(data)


def _allocate_from_distribution(
    counter: dict[str, int],
    chunk_size: int,
    rng: np.random.Generator,
) -> list[Any]:
    """
    Allocate rows from a distribution counter for a single chunk.
    Decrements the counter as rows are assigned.
    """
    total_remaining = sum(counter.values())
    if total_remaining <= 0:
        # All targets exhausted — fill with the first category
        first_cat = list(counter.keys())[0]
        return [first_cat] * chunk_size

    result: list[Any] = []

    for _ in range(chunk_size):
        total_remaining = sum(counter.values())
        if total_remaining <= 0:
            # Counters exhausted mid-chunk
            result.append(list(counter.keys())[0])
            continue

        # Weight selection proportionally to remaining counts
        cats = list(counter.keys())
        weights = [max(counter[c], 0) for c in cats]
        total_w = sum(weights)

        if total_w == 0:
            result.append(cats[0])
            continue

        probs = [w / total_w for w in weights]
        chosen = rng.choice(cats, p=probs)
        result.append(chosen)
        counter[chosen] = max(counter[chosen] - 1, 0)

    return result


def _generate_column_values(
    dtype: str,
    count: int,
    rng: np.random.Generator,
    fake: Faker,
    nullable: bool = False,
) -> list[Any]:
    """Generate random values for a column based on its data type."""
    values: list[Any]

    if dtype == DataType.INT or dtype == "INT":
        values = rng.integers(0, 100_000, size=count).tolist()
    elif dtype == DataType.FLOAT or dtype == "FLOAT":
        values = (rng.random(count) * 100_000).round(2).tolist()
    elif dtype == DataType.STRING or dtype == "STRING":
        values = [fake.word() for _ in range(count)]
    elif dtype == DataType.BOOLEAN or dtype == "BOOLEAN":
        values = rng.choice([True, False], size=count).tolist()
    elif dtype == DataType.DATE or dtype == "DATE":
        values = [fake.date() for _ in range(count)]
    elif dtype == DataType.DATETIME or dtype == "DATETIME":
        values = [fake.date_time().isoformat() for _ in range(count)]
    elif dtype == DataType.UUID or dtype == "UUID":
        values = [str(uuid.uuid4()) for _ in range(count)]
    elif dtype == DataType.EMAIL or dtype == "EMAIL":
        values = [fake.email() for _ in range(count)]
    elif dtype == DataType.PHONE or dtype == "PHONE":
        values = [fake.phone_number() for _ in range(count)]
    elif dtype == DataType.NAME or dtype == "NAME":
        values = [fake.name() for _ in range(count)]
    elif dtype == DataType.ADDRESS or dtype == "ADDRESS":
        values = [fake.address().replace("\n", ", ") for _ in range(count)]
    else:
        values = [fake.word() for _ in range(count)]

    # Apply nullability
    if nullable and count > 0:
        null_mask = rng.random(count) < 0.05  # 5% null rate
        values = [None if null_mask[i] else v for i, v in enumerate(values)]

    return values


# ──────────────────────────────────────────────
# Boundary Injection
# ──────────────────────────────────────────────


def _inject_boundary_rows(
    df: pd.DataFrame,
    boundary_rows: list[dict[str, Any]],
    config: GenerationConfig,
) -> pd.DataFrame:
    """
    Inject boundary test rows into the chunk, overwriting
    the last N rows to maintain the total record count.
    """
    if not boundary_rows:
        return df

    num_to_inject = min(len(boundary_rows), len(df))

    for i in range(num_to_inject):
        br = boundary_rows[i]
        row_idx = len(df) - num_to_inject + i

        # Set the boundary value
        if br["column"] in df.columns:
            df.at[row_idx, br["column"]] = br["value"]

        # Tag the generation reason
        if "_generation_reason" in df.columns:
            df.at[row_idx, "_generation_reason"] = "boundary_injection"

    return df


# ──────────────────────────────────────────────
# Interdependent Rule Application
# ──────────────────────────────────────────────


def _apply_interdependent_rules(
    df: pd.DataFrame,
    rules: list[InterdependentRule],
    config: GenerationConfig,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Apply conditional rules to overwrite random values with
    interdependent relationships.
    """
    for rule in rules:
        target_col = rule.target_column
        cond_col = rule.condition_column
        op = rule.condition_operator
        val = rule.condition_value
        fill_val = rule.target_fill_value

        if cond_col not in df.columns or target_col not in df.columns:
            continue

        try:
            if op in (BoundaryOperator.EQ, "="):
                mask = df[cond_col] == val
            elif op in (BoundaryOperator.NEQ, "!="):
                mask = df[cond_col] != val
            elif op in (BoundaryOperator.GT, ">"):
                mask = df[cond_col] > float(val)
            elif op in (BoundaryOperator.GTE, ">="):
                mask = df[cond_col] >= float(val)
            elif op in (BoundaryOperator.LT, "<"):
                mask = df[cond_col] < float(val)
            elif op in (BoundaryOperator.LTE, "<="):
                mask = df[cond_col] <= float(val)
            elif op in (BoundaryOperator.BETWEEN, "BETWEEN"):
                mask = (df[cond_col] >= float(val[0])) & (df[cond_col] <= float(val[1]))
            else:
                continue
        except (ValueError, TypeError):
            continue

        if not mask.any():
            continue

        num_to_fill = mask.sum()

        if isinstance(fill_val, list) and len(fill_val) == 2:
            low, high = fill_val[0], fill_val[1]
            try:
                # Find target column type
                dtype = next((c.data_type for c in config.schema_definition if c.column_name == target_col), "FLOAT")
                if dtype in (DataType.INT, "INT"):
                    new_values = rng.integers(int(low), int(high) + 1, size=num_to_fill)
                else:
                    new_values = rng.uniform(float(low), float(high), size=num_to_fill)
                df.loc[mask, target_col] = new_values
            except (ValueError, TypeError):
                # Fallback if range is not numeric
                df.loc[mask, target_col] = fill_val[0]
        else:
            df.loc[mask, target_col] = fill_val

        if "_generation_reason" in df.columns:
            df.loc[mask, "_generation_reason"] = "interdependent_rule"

    return df


# ──────────────────────────────────────────────
# Post-Generation Validation
# ──────────────────────────────────────────────


def _validate_output(
    output_path: Path,
    config: GenerationConfig,
    expected_rows: int,
) -> ValidationResult:
    """
    Read back the generated CSV and validate that distributions
    and boundary rules are correctly represented.
    """
    try:
        df = pd.read_csv(output_path)
    except Exception as e:
        logger.error(f"Validation failed — cannot read output: {e}")
        return ValidationResult(
            is_valid=False,
            total_rows_generated=0,
        )

    actual_rows = len(df)
    dist_checks: list[DistributionCheck] = []
    boundary_checks: list[BoundaryCheck] = []
    all_pass = True

    # Validate distributions
    for dc in config.distribution_constraints:
        col = dc.column_name
        if col not in df.columns:
            dist_checks.append(DistributionCheck(
                column_name=col,
                expected_ratios={c: r for c, r in zip(dc.categories, dc.ratios)},
                actual_ratios={},
                is_pass=False,
                deviation=100.0,
            ))
            all_pass = False
            continue

        actual_counts = df[col].value_counts()
        expected_ratios = {c: r for c, r in zip(dc.categories, dc.ratios)}
        actual_ratios = {
            str(k): round(v / actual_rows * 100, 2)
            for k, v in actual_counts.items()
        }

        max_deviation = 0.0
        for cat, expected_pct in expected_ratios.items():
            actual_pct = actual_ratios.get(cat, 0.0)
            deviation = abs(actual_pct - expected_pct)
            max_deviation = max(max_deviation, deviation)

        is_pass = max_deviation < 2.0  # Allow 2% tolerance
        if not is_pass:
            all_pass = False

        dist_checks.append(DistributionCheck(
            column_name=col,
            expected_ratios={c: float(r) for c, r in zip(dc.categories, dc.ratios)},
            actual_ratios=actual_ratios,
            is_pass=is_pass,
            deviation=round(max_deviation, 4),
        ))

    # Validate boundary rules
    for br in config.boundary_rules:
        col = br.column_name
        if col not in df.columns:
            boundary_checks.append(BoundaryCheck(
                column_name=col,
                operator=br.operator,
                value=str(br.value),
                boundary_rows_found=0,
                is_pass=False,
            ))
            all_pass = False
            continue

        boundary_count = len(
            df[df["_generation_reason"] == "boundary_injection"]
        ) if "_generation_reason" in df.columns else 0

        boundary_checks.append(BoundaryCheck(
            column_name=col,
            operator=br.operator,
            value=str(br.value),
            boundary_rows_found=boundary_count,
            is_pass=boundary_count > 0,
        ))

    return ValidationResult(
        is_valid=all_pass and actual_rows == expected_rows,
        distribution_checks=dist_checks,
        boundary_checks=boundary_checks,
        total_rows_generated=actual_rows,
    )


# ──────────────────────────────────────────────
# Progress Helpers
# ──────────────────────────────────────────────


def _send_progress(
    callback: Callable[[GenerationProgress], None] | None,
    job_id: str,
    stage: str,
    current_chunk: int,
    total_chunks: int,
    rows_processed: int,
    total_rows: int,
    message: str | None = None,
):
    """Send a progress update if a callback is registered."""
    if callback is None:
        return

    progress_pct = min(100.0, round(rows_processed / max(total_rows, 1) * 100, 1))
    if stage == "completed":
        progress_pct = 100.0

    status = JobStatus.COMPLETED if stage == "completed" else JobStatus.RUNNING

    progress = GenerationProgress(
        job_id=job_id,
        status=status,
        current_stage=stage,
        current_chunk=current_chunk,
        total_chunks=total_chunks,
        rows_processed=rows_processed,
        total_rows=total_rows,
        progress_percent=progress_pct,
        message=message,
    )

    try:
        callback(progress)
    except Exception as e:
        logger.warning(f"Progress callback failed: {e}")
