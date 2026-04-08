# Deterministic Synthetic Data Engine Implementation Plan

**Goal**: Build a fully **stateless** Deterministic Synthetic Data Engine over a 15-day timeline utilizing core Python (FastAPI) and React. This engine leverages an Actor-Critic LLM chain for configuration generation, extracting data schemas directly from CSVs, and executing mathematical generation via a multi-threaded Pandas architecture with **global distribution pre-calculation** and memory-safe chunking for seamless WebSocket streaming.

## User Review Required

> [!IMPORTANT]
> **Stateless Architecture**: MongoDB has been fully removed. The React frontend holds the drafted JSON configuration in component state during the human-in-the-loop review. The backend is entirely stateless—no database, no session storage. The only persistence is a local Docker volume for `.csv` chunk exports.

> [!IMPORTANT]
> **Endpoint Change**: The approval trigger has changed from `POST /api/config/{id}/approve` to `POST /api/execute-generation`. This new endpoint accepts the **entire approved JSON configuration** in the request body, removing any need for server-side config lookup.

> [!TIP]
> The UI will use **shadcn/ui** to provide rapidly deployable, premium components (Data Tables, Accordions, Progress bars) for the dashboard while remaining customizable via Tailwind CSS.

## Proposed Changes

### 1. Technology Choices
- **Frontend**: React (Vite), Tailwind CSS, shadcn/ui, WebSockets.
- **Backend**: Python, FastAPI, WebSockets, Pydantic, Pandas, NumPy, Faker, `asyncio`.
- **Persistence**: Local Docker Volume only — for exporting generated `.csv` datasets. No database.
- **LLM Integration**: OpenAI/Gemini API via an Actor-Critic architecture with Strict JSON Response mode.
- **CSV Data Model Parsing**: Pandas for explicit schema extraction from CSV uploads (Optimized: reads only the first 5 rows).
- **Deployment**: Docker Compose for local containerized development (Frontend + Backend containers only).

### 2. File and Directory Structure
- `/frontend`: React + Vite client source code.
- `/backend`: Python FastAPI application source code.
- `/docker-compose.yml`: For managing frontend and backend containers.
- `/data-volumes`: Local mount for chunked `.csv` exports.

### 3. Backend Core Design (100% Stateless)
- **Schemas**: Strict Pydantic models mapping the Data Model (columns), DistributionConstraints, and BoundaryRules.
- **No Database**: The backend does not persist configurations. It receives, validates, and executes — nothing is stored server-side.
- **CSV Schema Parsing**: FastAPI endpoints accept a multipart file upload. Pandas extracts the column headers and inferred data types from *only the first 5-10 rows* of the CSV to prevent memory exhaustion on large files, establishing a "Source of Truth".
- **Actor-Critic AI Orchestration**:
    - **System Prompts**: Highly engineered and version-controlled instructions forcing rigid JSON outputs.
    - **Step 1 (The Actor)**: The `POST /api/generate-draft-config` endpoint invokes the primary LLM with the user's natural language prompt and the extracted CSV headers. It drafts a Pydantic-compliant JSON configuration and returns it directly to the frontend.
    - **Step 2 (The Critic)**: A secondary LLM reviews the Actor's drafted JSON. The Critic evaluates for edge logical conflicts and validates that all distribution ratio sets dynamically sum to precisely 100%.
    - **Retry Limit**: A loop executes with `MAX_RETRIES = 2`. If the Critic spots errors, its feedback gets appended to the prompt, re-triggering the Actor.
    - **Graceful Degradation (Fallback)**: If the Critic still rejects the draft post-limit, the endpoint breaks the loop, absorbs the Actor's latest draft, and appends a `requires_manual_review: true` flag.
- **Stateless Execution Trigger**: The `POST /api/execute-generation` endpoint accepts the **full approved JSON configuration** in the request body. The frontend is the sole owner of the config state and transmits it in its entirety when the user clicks "Generate".
    - Determinism is enforced by hashing `config_id` to seed `np.random` and `Faker`.
    - **Global Distribution Pre-Calculation**: Before entering the chunking loop, the engine computes **exact global row targets** for every distribution constraint (e.g., exactly 200,000 "Tier A" rows out of 1,000,000 total). These targets are stored as mutable counters and passed into the chunk loop. Each chunk decrements the counters as it allocates rows, guaranteeing that the final aggregated dataset has **mathematically perfect distribution ratios** regardless of chunk size.
    - **Memory Chunking**: Pandas operates in configurable block sizes (e.g., 100k rows/chunk). Completed chunks are incrementally appended to disk via streams to preserve RAM.
    - **Threading**: The engine executes asynchronously on a separate thread via `asyncio.to_thread()`, ensuring uninterrupted WebSocket telemetries.
    - **Data Pipeline Steps (per chunk)**: Row Allocation (using global counters) → Boundary Injection → Interdependent Row Filling → `_generation_reason` Tagging → Flush to disk.

### 4. Frontend Application Design (State Owner)
- **State Management**: The React frontend is the **single source of truth** for the JSON configuration. After the Actor-Critic endpoint returns a draft, the config is stored in React state. The user edits it, and upon approval the entire object is `POST`ed to `/api/execute-generation`.
- **Builder Dashboard**: Uses **shadcn/ui** components. A workspace beginning with a **CSV Upload Zone**. Uploading a file displays the parsed tabular headers. The user enters an NL prompt, kicking off the Actor-Critic AI drafting. The backend response populates an **Accordion-styled** configuration viewer.
- **WebSocket State Management**: Incorporates a **throttle/debounce mechanism**. Incoming WebSocket generation states are batched (e.g., triggering a React re-render every 250ms rather than every row) eliminating renderer lock-up and browser crashes.
- **Execution & Observability Dash**: Actively listens to WebSocket streams displaying live progress bars and real-time metrics.

## Verification Plan

### Automated Tests
- Integration tests executing the Pandas engine repeatedly with identical `config_id` values to assert 100% determinism.
- **Distribution Accuracy Test**: Generate a 1M-row dataset in chunks, then read back the final `.csv` and assert that the actual distribution ratios match the config's requested ratios to the exact row count.
- Simulation checks invoking the `asyncio` worker heavily while pinging the Event Loop to verify WebSocket telemetry does not drop out under load.
- Unit testing isolating the Critic LLM node to assure it detects deliberately conflicting constraints.

### Manual Verification
- Upload an extremely large sample dataset CSV (e.g., 2GB) through the UI, ensuring the backend reads headers within fractions of a second via the "first 5 rows" optimization.
- Monitor background console logging, ensuring the Actor-Critic pipeline intervenes correctly.
- Run a multi-million record synthetic output trace while connected via WebSockets, observing the frontend RAM via devtools to ensure the UI WebSocket throttle prevents browser crashes.
- Verify stateless behavior: restart the backend container mid-session and confirm that the frontend still holds its config and can re-submit to `/api/execute-generation` without data loss.
