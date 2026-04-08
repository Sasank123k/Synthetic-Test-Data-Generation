# Deterministic Synthetic Data Engine Tasks

## Phase 1: Project Setup & Infrastructure
- [x] Initialize frontend application (React, Vite, Tailwind CSS)
- [ ] Install and configure **shadcn/ui** component framework (deferred post-MVP)
- [x] Initialize backend application (FastAPI, Python)
- [x] Add Pandas, NumPy, Faker dependencies
- [x] Configure Docker & Docker Compose (Frontend + Backend containers only, no DB)
- [x] Create local Docker Volume mount (`/data-volumes`) for `.csv` exports

## Phase 2: Backend Core & Pydantic Schemas
- [x] Implement Pydantic configuration schemas (DataModel, DistributionConstraints, BoundaryRules)
- [x] Design and version-control strict System Prompts for Actor (JSON mapping) and Critic (Constraint logic)
- [x] Create `POST /api/generate-draft-config` endpoint stub (returns config directly to frontend, no DB write)
- [x] Create `POST /api/execute-generation` endpoint stub (accepts full JSON config in request body)

## Phase 3: AI Orchestration & Actor-Critic Chain
- [x] Implement `POST /api/generate-draft-config` to handle multipart/form-data for CSV files
- [x] Implement **Optimized CSV Schema Extraction** (Read only first 5 rows to infer Headers & Types)
- [x] Implement Step 1 (Actor): LLM call to draft Pydantic-compliant JSON config using prompt + CSV headers
- [x] Implement Step 2 (Critic): Second LLM call to review drafted JSON for logical conflicts and distribution sum (100%)
- [x] Implement Actor-Critic retry loop (`MAX_RETRIES = 2`) appending critic feedback to the actor on failure
- [x] Implement Graceful Degradation fallback (`requires_manual_review: true`) avoiding 500 errors if retries exhaust

## Phase 4: Deterministic Data Engine (with Global Distribution Math)
- [x] Implement Pandas engine seeding (Faker & np.random via hashed `config_id`)
- [x] **Global Distribution Pre-Calculation**: Before chunking, compute exact global row targets for every distribution constraint (e.g., 200,000 "Tier A" out of 1,000,000) and store as mutable counters
- [x] Setup **Memory Management / Chunking Engine**: Loop generation logic in configurable blocks (e.g., 100k rows/chunk)
- [x] Step 1: Implement distribution allocation logic per chunk, **decrementing global counters** to guarantee perfect final ratios
- [x] Step 2: Implement boundary rule injection logic per chunk
- [x] Step 3: Implement interdependent logic row filling per chunk
- [x] Step 4: Add `_generation_reason` observability tagging
- [x] **Disk IO**: Append finished chunks incrementally to a `.csv` file in the persistent Docker volume mount, freeing RAM after each chunk

## Phase 5: Observable Generation Workflow
- [x] Implement background task runner for data generation using `asyncio.to_thread` to keep the event loop non-blocking
- [x] Implement WebSockets in FastAPI for streaming progress statistics (rows processed, current stage, chunk number)
- [x] Create download endpoint for finalized datasets (`GET /api/export/{job_id}`) targeting the generated local file

## Phase 6: Frontend Development (State Owner)
- [x] Implement CSV Upload zone and display extracted headers using shadcn/ui Data Tables
- [x] Implement Configuration Builder View (NL Prompt Input + Accordion Edit Form)
- [x] Implement **frontend state ownership**: store drafted JSON config in React state, allow user edits
- [x] Implement Approval workflow: on "Generate", `POST` the full config object to `/api/execute-generation`
- [x] Implement Observability Dashboard View (Live WebSocket stats with progress bars)
- [x] **State Optimization**: Implement a React Throttle/Debouncer on the WebSocket listener to cap DOM-renders to 250ms intervals

## Phase 7: Verification & Testing
- [x] Test backend CSV parsing performance with an artificially large >1GB file (should parse in <1s)
- [x] **Distribution Accuracy Test**: Generate a 1M-row dataset in chunks, read back final `.csv`, assert exact row-count accuracy vs. config ratios
- [x] Verify deterministic behavior: run same config twice, assert byte-identical output
- [x] Test stateless resilience: restart backend container, confirm frontend still holds config and can re-submit
- [x] Test UI stability under intense WebSocket load to confirm throttling works
- [x] End-to-End manual testing of full configuration generation flow
- [ ] Final UI Polish (post-MVP)
