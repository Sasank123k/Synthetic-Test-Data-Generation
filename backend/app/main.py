"""
FastAPI Application Entry Point

Stateless backend — no database, no persistent storage of configurations.
The React frontend holds all config state and sends the full approved
payload to POST /api/execute-generation for processing.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import settings

# ──────────────────────────────────────────────
# Application Factory
# ──────────────────────────────────────────────

app = FastAPI(
    title="Synthetic Data Engine",
    description=(
        "Deterministic Synthetic Data Generation Engine. "
        "Translates natural language prompts into structured JSON configs "
        "via an Actor-Critic LLM chain, then generates exact datasets "
        "using a seeded Pandas engine."
    ),
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ──────────────────────────────────────────────
# CORS Middleware
# ──────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────
# Register Routers
# ──────────────────────────────────────────────

try:
    from app.routers import csv_router, config_router, generation_router, ws_router
    app.include_router(csv_router)
    app.include_router(config_router)
    app.include_router(generation_router)
    app.include_router(ws_router)  # WebSocket for progress streaming
    print("[STARTUP] All routers registered successfully (including WebSocket)")
except Exception as e:
    import traceback
    with open("startup_error.txt", "w") as f:
        f.write(f"[STARTUP ERROR] Failed to register routers: {e}\n")
        traceback.print_exc(file=f)
    print(f"[STARTUP ERROR] Written to startup_error.txt")

# ──────────────────────────────────────────────
# Health Check
# ──────────────────────────────────────────────


@app.get("/api/health", tags=["System"])
async def health_check():
    """
    Health check endpoint.
    Returns service status and active LLM provider configuration.
    """
    return {
        "status": "ok",
        "service": "synthetic-data-engine",
        "version": "0.1.0",
        "llm_provider": settings.llm_provider,
        "llm_model": (
            settings.openai_model
            if settings.llm_provider == "openai"
            else settings.gemini_model
        ),
    }


# ──────────────────────────────────────────────
# Startup Event
# ──────────────────────────────────────────────


@app.on_event("startup")
async def startup_event():
    """Log startup configuration."""
    print("=" * 60)
    print("  Synthetic Data Engine — Starting Up")
    print(f"  LLM Provider : {settings.llm_provider}")
    print(f"  LLM Model    : {settings.openai_model if settings.llm_provider == 'openai' else settings.gemini_model}")
    print(f"  Data Volume  : {settings.data_volume_path}")
    print(f"  CORS Origin  : {settings.frontend_url}")
    print("=" * 60)
