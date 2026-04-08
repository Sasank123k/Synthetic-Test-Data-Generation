"""
Generation Router — Background Execution + WebSocket Streaming + CSV Export

Endpoints:
  POST /api/execute-generation  → Launches background data engine
  GET  /api/export/{job_id}     → Downloads the generated CSV file
  WS   /ws/generation/{job_id}  → Real-time progress streaming

The generation runs on a separate thread via asyncio.to_thread()
to keep the FastAPI event loop free for WebSocket telemetry.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse

from app.config import settings
from app.schemas.generation import (
    GenerationRequest,
    GenerationJobResponse,
    GenerationProgress,
    JobStatus,
)
from app.services.data_engine import run_generation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Generation"])


# ──────────────────────────────────────────────
# In-Memory Job State (no database needed)
# ──────────────────────────────────────────────

# Maps job_id → job metadata + latest progress
_active_jobs: dict[str, dict[str, Any]] = {}

# Maps job_id → list of WebSocket connections
_job_subscribers: dict[str, list[asyncio.Queue]] = {}


# ──────────────────────────────────────────────
# POST /api/execute-generation
# ──────────────────────────────────────────────


@router.post(
    "/execute-generation",
    response_model=GenerationJobResponse,
    summary="Execute synthetic data generation",
    description=(
        "Submit the fully approved configuration to start data generation. "
        "The engine runs in the background; track progress via WebSocket "
        "at ws://host/ws/generation/{job_id}.\n\n"
        "Returns immediately with a job_id for tracking."
    ),
)
async def execute_generation(request: GenerationRequest) -> GenerationJobResponse:
    """Launch the deterministic data engine as a background task."""
    job_id = str(uuid.uuid4())

    total_records = request.config.total_records
    chunk_size = request.chunk_size
    total_chunks = math.ceil(total_records / chunk_size)

    # Register job in memory
    _active_jobs[job_id] = {
        "status": JobStatus.QUEUED,
        "total_records": total_records,
        "total_chunks": total_chunks,
        "config": request.config,
        "chunk_size": chunk_size,
        "output_path": None,
        "error": None,
        "validation": None,
        "latest_progress": None,
    }

    # Launch background generation
    asyncio.create_task(_run_generation_background(job_id, request))

    logger.info(
        f"[Job {job_id}] Generation queued: {total_records:,} records, "
        f"{total_chunks} chunk(s)"
    )

    return GenerationJobResponse(
        job_id=job_id,
        status=JobStatus.QUEUED,
        message=(
            f"Generation job queued: {total_records:,} records "
            f"across {total_chunks} chunk(s) of {chunk_size:,} rows each. "
            f"Config has {len(request.config.schema_definition)} columns, "
            f"{len(request.config.distribution_constraints)} distribution constraints, "
            f"and {len(request.config.boundary_rules)} boundary rules."
        ),
        total_records=total_records,
        total_chunks=total_chunks,
    )


# ──────────────────────────────────────────────
# GET /api/export/{job_id}
# ──────────────────────────────────────────────


@router.get(
    "/export/{job_id}",
    summary="Download generated dataset",
    description="Download the generated CSV file for a completed job.",
    tags=["Export"],
)
async def export_dataset(job_id: str):
    """Stream the generated CSV file to the client."""
    job = _active_jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    if job["status"] == JobStatus.QUEUED:
        return {
            "job_id": job_id,
            "status": "queued",
            "message": "Generation has not started yet. Please wait.",
        }

    if job["status"] == JobStatus.RUNNING:
        progress = job.get("latest_progress")
        pct = progress.progress_percent if progress else 0
        return {
            "job_id": job_id,
            "status": "running",
            "message": f"Generation in progress ({pct}% complete). Please wait.",
        }

    if job["status"] == JobStatus.FAILED:
        raise HTTPException(
            status_code=500,
            detail=f"Generation failed: {job.get('error', 'Unknown error')}",
        )

    # Status is COMPLETED
    output_path = job.get("output_path")
    if not output_path or not Path(output_path).exists():
        raise HTTPException(
            status_code=404,
            detail=f"Generated file not found at {output_path}",
        )

    return FileResponse(
        path=output_path,
        media_type="text/csv",
        filename=f"synthetic_data_{job_id}.csv",
        headers={"Content-Disposition": f'attachment; filename="synthetic_data_{job_id}.csv"'},
    )


# ──────────────────────────────────────────────
# GET /api/job-status/{job_id}
# ──────────────────────────────────────────────


@router.get(
    "/job-status/{job_id}",
    summary="Get job status",
    description="Get the current status of a generation job.",
    tags=["Generation"],
)
async def get_job_status(job_id: str):
    """Return the current status and progress of a generation job."""
    job = _active_jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    progress = job.get("latest_progress")
    validation = job.get("validation")

    return {
        "job_id": job_id,
        "status": job["status"],
        "total_records": job["total_records"],
        "total_chunks": job["total_chunks"],
        "output_path": job.get("output_path"),
        "error": job.get("error"),
        "progress": progress.model_dump() if progress else None,
        "validation": validation.model_dump() if validation else None,
    }


# ──────────────────────────────────────────────
# WebSocket /ws/generation/{job_id}
# ──────────────────────────────────────────────


ws_router = APIRouter()  # Separate router for WS (no prefix needed)


@ws_router.websocket("/ws/generation/{job_id}")
async def websocket_generation_progress(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint for real-time generation progress streaming.

    The client connects and receives JSON progress updates as the
    engine processes each chunk/stage. The connection closes when
    the job completes or fails.
    """
    await websocket.accept()

    job = _active_jobs.get(job_id)
    if not job:
        await websocket.send_json({
            "error": f"Job '{job_id}' not found"
        })
        await websocket.close()
        return

    # Create a queue for this subscriber
    queue: asyncio.Queue = asyncio.Queue()
    if job_id not in _job_subscribers:
        _job_subscribers[job_id] = []
    _job_subscribers[job_id].append(queue)

    logger.info(f"[WS] Client connected to job {job_id}")

    try:
        # If job already completed, send final status and close
        if job["status"] in (JobStatus.COMPLETED, JobStatus.FAILED):
            progress = job.get("latest_progress")
            if progress:
                await websocket.send_json(progress.model_dump())
            await websocket.close()
            return

        # Stream progress updates
        while True:
            try:
                # Wait for progress with timeout to detect disconnects
                progress = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(progress.model_dump())

                # Close connection if job is done
                if progress.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                    break

            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                try:
                    await websocket.send_json({"heartbeat": True})
                except Exception:
                    break

    except WebSocketDisconnect:
        logger.info(f"[WS] Client disconnected from job {job_id}")
    except Exception as e:
        logger.error(f"[WS] Error streaming to job {job_id}: {e}")
    finally:
        # Clean up subscriber
        if job_id in _job_subscribers:
            try:
                _job_subscribers[job_id].remove(queue)
            except ValueError:
                pass
            if not _job_subscribers[job_id]:
                del _job_subscribers[job_id]


# ──────────────────────────────────────────────
# Background Task Runner
# ──────────────────────────────────────────────


async def _run_generation_background(
    job_id: str,
    request: GenerationRequest,
):
    """
    Run the data engine on a separate thread via asyncio.to_thread().
    Streams progress updates to WebSocket subscribers.
    """
    _active_jobs[job_id]["status"] = JobStatus.RUNNING

    # Create a thread-safe progress callback
    loop = asyncio.get_event_loop()

    def progress_callback(progress: GenerationProgress):
        """Thread-safe callback that pushes to WebSocket queues."""
        _active_jobs[job_id]["latest_progress"] = progress

        # Push to all WebSocket subscribers
        if job_id in _job_subscribers:
            for q in _job_subscribers[job_id]:
                try:
                    loop.call_soon_threadsafe(q.put_nowait, progress)
                except Exception:
                    pass

    try:
        # Run the synchronous engine on a separate thread
        result = await asyncio.to_thread(
            run_generation,
            config=request.config,
            job_id=job_id,
            chunk_size=request.chunk_size,
            progress_callback=progress_callback,
        )

        # Update job state
        _active_jobs[job_id]["status"] = JobStatus.COMPLETED
        _active_jobs[job_id]["output_path"] = result["output_path"]
        _active_jobs[job_id]["validation"] = result.get("validation")

        logger.info(
            f"[Job {job_id}] Completed: {result['total_rows']:,} rows → "
            f"{result['output_path']}"
        )

    except Exception as e:
        logger.error(f"[Job {job_id}] Failed: {e}", exc_info=True)
        _active_jobs[job_id]["status"] = JobStatus.FAILED
        _active_jobs[job_id]["error"] = str(e)

        # Notify WebSocket subscribers of failure
        fail_progress = GenerationProgress(
            job_id=job_id,
            status=JobStatus.FAILED,
            current_stage="failed",
            current_chunk=0,
            total_chunks=_active_jobs[job_id]["total_chunks"],
            rows_processed=0,
            total_rows=_active_jobs[job_id]["total_records"],
            progress_percent=0,
            message=f"Generation failed: {str(e)}",
        )
        if job_id in _job_subscribers:
            for q in _job_subscribers[job_id]:
                try:
                    loop.call_soon_threadsafe(q.put_nowait, fail_progress)
                except Exception:
                    pass
