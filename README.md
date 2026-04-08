# 🧪 Synthetic Data Engine

> **Deterministic, explainable, and repeatable synthetic test data generation** — powered by an AI Actor-Critic pipeline with human-in-the-loop approval.

Describe your test data scenario in plain English. The engine translates it into a strict JSON configuration via an AI pipeline (Gemini / OpenAI), then generates a deterministic dataset with **mathematically perfect distribution ratios**, **boundary edge-case injection**, and **full observability**.

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| **NL2Config AI Pipeline** | Actor-Critic LLM chain that translates natural language prompts into validated JSON configurations |
| **Deterministic Engine** | Same `config_id` always produces **byte-identical output** — seeded via SHA-256 |
| **Distribution Precision** | Global pre-calculation ensures **0% deviation** in category ratios (e.g., 60/25/15 splits) |
| **Boundary Injection** | Automatically injects edge-case rows for each boundary rule (e.g., `score = 699, 700, 701` for `score > 700`) |
| **Real-time Streaming** | WebSocket-based live progress updates during generation |
| **Observability** | Every row is tagged with `_generation_reason` (distribution_allocation, boundary_injection) |
| **Stateless Architecture** | No database — frontend owns config state, backend is pure compute |
| **Human-in-the-Loop** | Review, edit, and approve AI-generated configurations before generation |

---

## 🏗️ Architecture

```
┌─────────────────────────┐          ┌──────────────────────────────────────┐
│                         │          │          FastAPI Backend (:8001)      │
│   React Frontend        │          │                                      │
│   (:5173)               │          │  ┌────────────────────────────────┐  │
│                         │  REST    │  │   Actor-Critic LLM Pipeline    │  │
│  ┌───────────────────┐  │ ◄──────► │  │                                │  │
│  │ Step 1: Upload    │  │          │  │  Actor ──► Critic ──► Retry    │  │
│  │ Step 2: Configure │  │          │  │  (Gemini 2.5 Flash)            │  │
│  │ Step 3: Generate  │  │          │  └────────────────────────────────┘  │
│  │ Step 4: Results   │  │          │                                      │
│  └───────────────────┘  │  WS     │  ┌────────────────────────────────┐  │
│                         │ ◄──────► │  │   Deterministic Data Engine    │  │
│  Config state lives     │          │  │                                │  │
│  entirely in React      │          │  │  Seeded RNG ──► Pandas Chunks  │  │
│                         │          │  │  ──► Distribution Allocation   │  │
│                         │          │  │  ──► Boundary Injection        │  │
│                         │          │  │  ──► CSV Flush to Disk         │  │
│                         │          │  └──────────────┬─────────────────┘  │
│                         │  CSV     │                 │                    │
│                         │ ◄──────  │           ┌─────▼──────┐            │
│                         │          │           │  CSV File   │            │
└─────────────────────────┘          │           │ data-volumes │            │
                                     │           └─────────────┘            │
                                     └──────────────────────────────────────┘
```

### Data Flow

```
  User Prompt                  AI Actor-Critic              Deterministic Engine
  ───────────                  ───────────────              ────────────────────
 "Generate credit        ┌──► Actor LLM ──────┐        ┌──► Seed from config_id
  scoring data with      │    (Draft JSON)     │        │    (SHA-256 hash)
  60/25/15 split..."     │         │           │        │         │
       │                 │    Pydantic Parse    │        │    Pre-calculate global
       ▼                 │         │           │        │    distribution targets
  POST /generate-        │    Critic LLM       │        │         │
  draft-config ──────────┘    (Review)         │        │    Allocate per chunk
       │                      │           │    │        │    (decrement counters)
       │                 Pass ▼      Fail ▼    │        │         │
       │                 Return    Retry (×2)  │        │    Inject boundary rows
       │                 Config    with feedback│        │    (val-1, val, val+1)
       │                      │                │        │         │
       ▼                      ▼                │        │    Tag _generation_reason
  Review & Edit ◄──── DraftConfigResponse      │        │         │
  in Browser                                   │        │    Flush chunk to CSV
       │                                       │        │         │
       ▼                                       │        │    Validate output
  POST /execute-generation ────────────────────┘────────┘         │
       │                                                          ▼
       ▼                                                   ValidationResult
  WebSocket Progress ◄──── Real-time updates              (distribution checks,
       │                   from engine                     boundary checks)
       ▼
  Download CSV
```

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | React 19, TypeScript, Vite, Tailwind CSS | 4-step wizard UI |
| **Backend** | Python 3.12, FastAPI, Pydantic v2 | Stateless API server |
| **AI / LLM** | Google Gemini 2.5 Flash (default), OpenAI GPT-4o (swappable) | NL2Config translation |
| **Data Engine** | Pandas, NumPy, Faker | Deterministic data generation |
| **Streaming** | WebSockets | Real-time generation progress |
| **Persistence** | File system (CSV) | No database required |

---

## 🚀 Runbook — Setup & Run

### Prerequisites

| Requirement | Version | Check Command |
|-------------|---------|---------------|
| **Python** | 3.12+ | `python --version` |
| **Node.js** | 20+ | `node --version` |
| **npm** | 10+ | `npm --version` |
| **Git** | Any | `git --version` |
| **API Key** | Gemini or OpenAI | See Step 3 below |

### Step 1 — Clone the Repository

```bash
git clone https://github.com/Sasank123k/Synthetic-Test-Data-Generation.git
cd Synthetic-Test-Data-Generation
```

### Step 2 — Setup the Backend

```bash
# Navigate to backend
cd backend

# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# ── Windows (PowerShell) ──
.\venv\Scripts\Activate.ps1

# ── Windows (CMD) ──
.\venv\Scripts\activate.bat

# ── macOS / Linux ──
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### Step 3 — Configure Environment Variables

```bash
# Create the .env file from the example template
cp .env.example .env      # macOS/Linux
copy .env.example .env     # Windows CMD
```

Edit `backend/.env` and configure your **LLM API key**:

```env
# ── LLM Provider (choose one) ──
LLM_PROVIDER=gemini                          # Options: "gemini" or "openai"

# ── Gemini Configuration (recommended) ──
GEMINI_API_KEY=your-google-api-key-here      # Get from: https://aistudio.google.com/apikey
GEMINI_MODEL=gemini-2.5-flash

# ── OpenAI Configuration (alternative) ──
# OPENAI_API_KEY=sk-your-openai-key-here
# OPENAI_MODEL=gpt-4o

# ── Engine Settings ──
MAX_RETRIES=2                                 # Actor-Critic retry limit
DATA_VOLUME_PATH=./data-volumes               # Where generated CSVs are saved

# ── Server ──
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8001
FRONTEND_URL=http://localhost:5173
```

> **Getting a Gemini API Key:**
> 1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
> 2. Click "Create API Key"
> 3. Copy the key and paste it as `GEMINI_API_KEY` in your `.env` file

### Step 4 — Start the Backend

```bash
# Make sure you're in the backend/ directory with venv activated
python run.py
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
```

Verify at: [http://localhost:8001/api/health](http://localhost:8001/api/health)

### Step 5 — Setup the Frontend

Open a **new terminal window**:

```bash
# Navigate to frontend
cd frontend

# Install Node.js dependencies
npm install

# Start the development server
npm run dev
```

You should see:
```
VITE v6.x.x ready in XXX ms
  ➜  Local:   http://localhost:5173/
```

### Step 6 — Open the Application

Open your browser and go to: **[http://localhost:5173](http://localhost:5173)**

You should see:
- ✅ "Synthetic Data Engine" header
- ✅ Green health indicator showing `gemini/gemini-2.5-flash` in the top-right
- ✅ 4-step progress bar: Upload & Prompt → Review Config → Generate → Results

---

## 📖 Usage Guide

### 1. Upload CSV (Optional)

Drop a sample CSV file to extract column headers. The engine reads only the first 5 rows for schema extraction — safe for files of any size.

### 2. Describe Your Data

Enter a natural language prompt describing the synthetic data you need:

```
Generate credit scoring test data with 60% prime borrowers, 25% near-prime,
and 15% sub-prime. Include credit_score (INT), annual_income (FLOAT),
risk_tier (STRING), and is_approved (BOOLEAN) columns.
```

Set the desired total record count and click **Generate Config →**.

### 3. Review & Edit Configuration

The AI generates a strict JSON configuration with:
- **Schema Definition** — column names, data types, nullable flags
- **Distribution Constraints** — category ratios (must sum to 100%)
- **Boundary Rules** — edge-case test values to inject

Review the configuration. Edit the total records if needed. Click **Approve & Generate**.

### 4. Monitor & Download

- Watch real-time progress via WebSocket streaming
- View validation results (distribution accuracy, boundary rule coverage)
- Download the generated CSV file

---

## 🔌 API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | `GET` | Health check — returns service status, LLM provider info |
| `/api/extract-schema` | `POST` | Upload a CSV file → returns column schema (names, types, samples) |
| `/api/generate-draft-config` | `POST` | NL prompt + CSV → AI-generated JSON config via Actor-Critic chain |
| `/api/execute-generation` | `POST` | Submit approved config → starts background generation job |
| `/api/job-status/{job_id}` | `GET` | Poll job status, progress, and validation results |
| `/api/export/{job_id}` | `GET` | Download the generated CSV file |
| `/ws/generation/{job_id}` | `WebSocket` | Real-time generation progress streaming |

### Example: Generate Data via API

```bash
# 1. Generate a draft config from a prompt
curl -X POST http://localhost:8001/api/generate-draft-config \
  -F "prompt=Generate 500 rows of user data with 70% active, 30% inactive status" \
  -F "total_records=500"

# 2. Execute generation with the returned config
curl -X POST http://localhost:8001/api/execute-generation \
  -H "Content-Type: application/json" \
  -d '{"config": { ... }, "chunk_size": 100000}'

# 3. Download the CSV
curl -O http://localhost:8001/api/export/{job_id}
```

Full Swagger documentation available at: [http://localhost:8001/docs](http://localhost:8001/docs)

---

## 📁 Project Structure

```
Synthetic-Test-Data-Generation/
├── README.md                          # This file
├── .gitignore                         # Git ignore rules
├── .env.example                       # Root environment template
│
├── backend/                           # FastAPI Backend (Python)
│   ├── run.py                         # Entry point (uvicorn launcher)
│   ├── requirements.txt               # Python dependencies
│   ├── .env                           # Local environment config (git-ignored)
│   │
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app, CORS, router registration
│   │   ├── config.py                  # Pydantic Settings (reads .env)
│   │   │
│   │   ├── schemas/                   # Pydantic Data Contracts
│   │   │   ├── config.py              # GenerationConfig, ColumnDefinition,
│   │   │   │                          #   DistributionConstraint, BoundaryRule
│   │   │   ├── generation.py          # GenerationProgress, ValidationResult,
│   │   │   │                          #   JobStatus, GenerationJobResponse
│   │   │   └── csv_schema.py          # CsvColumnInfo, CsvSchemaResponse
│   │   │
│   │   ├── routers/                   # API Route Modules
│   │   │   ├── config_router.py       # POST /api/generate-draft-config
│   │   │   ├── csv_router.py          # POST /api/extract-schema
│   │   │   └── generation_router.py   # POST /api/execute-generation,
│   │   │                              #   GET /api/job-status, /api/export,
│   │   │                              #   WebSocket /ws/generation/{job_id}
│   │   │
│   │   └── services/                  # Business Logic
│   │       ├── llm_client.py          # LLM factory (Gemini / OpenAI)
│   │       ├── orchestrator.py        # Actor-Critic pipeline with retries
│   │       ├── data_engine.py         # Deterministic Pandas generation engine
│   │       └── prompts/               # Version-controlled LLM prompts
│   │           ├── actor_prompt.py    # Actor system prompt
│   │           └── critic_prompt.py   # Critic system prompt
│   │
│   ├── data-volumes/                  # Generated CSV output directory
│   ├── test_endpoints.py              # Phase 3 API smoke tests
│   └── test_phase4_5.py               # Phase 4+5 engine + export tests
│
├── frontend/                          # React Frontend (TypeScript)
│   ├── package.json                   # Node.js dependencies
│   ├── vite.config.ts                 # Vite config with API proxy to :8001
│   ├── tailwind.config.js             # Tailwind CSS configuration
│   ├── tsconfig.json                  # TypeScript config
│   ├── index.html                     # HTML entry point
│   │
│   └── src/
│       ├── main.tsx                   # React DOM mount
│       ├── App.tsx                    # Main app — 4-step wizard
│       ├── index.css                  # Tailwind + dark theme variables
│       │
│       ├── lib/
│       │   ├── types.ts               # TypeScript types (mirrors Pydantic)
│       │   ├── api.ts                 # Typed API client (fetch wrappers)
│       │   └── utils.ts               # Utility functions (cn)
│       │
│       └── hooks/
│           └── useWebSocket.ts        # WebSocket hook with 250ms throttle
│
└── data-volumes/                      # Root-level CSV output (git-ignored)
```

---

## ⚙️ Environment Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `LLM_PROVIDER` | `gemini` | ✅ | LLM provider: `gemini` or `openai` |
| `GEMINI_API_KEY` | — | ✅* | Google Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | No | Gemini model identifier |
| `OPENAI_API_KEY` | — | ✅* | OpenAI API key (if using OpenAI) |
| `OPENAI_MODEL` | `gpt-4o` | No | OpenAI model identifier |
| `MAX_RETRIES` | `2` | No | Actor-Critic retry limit before graceful degradation |
| `DATA_VOLUME_PATH` | `./data-volumes` | No | Directory for generated CSV exports |
| `BACKEND_HOST` | `0.0.0.0` | No | Backend bind host |
| `BACKEND_PORT` | `8001` | No | Backend bind port |
| `FRONTEND_URL` | `http://localhost:5173` | No | Frontend URL for CORS |

*\* One of `GEMINI_API_KEY` or `OPENAI_API_KEY` is required depending on `LLM_PROVIDER`.*

---

## 🧪 Running Tests

### Backend API Tests

```bash
cd backend

# Activate virtual environment
.\venv\Scripts\Activate.ps1    # Windows
source venv/bin/activate        # macOS/Linux

# Start the backend (in a separate terminal)
python run.py

# Run Phase 3 tests (LLM + API endpoints)
python test_endpoints.py

# Run Phase 4+5 tests (Engine + WebSocket + Export + Determinism)
python test_phase4_5.py
```

### Expected Test Output

```
============================================================
  Phase 4+5 End-to-End Test Suite
============================================================

=== Test 1: POST /api/execute-generation  ===  PASS
=== Test 2: Poll /api/job-status           ===  PASS  (Distribution deviation: 0.0%)
=== Test 3: GET /api/export                ===  PASS  (1000 rows, 73KB CSV)
=== Test 4: Distribution Accuracy          ===  PASS  (Prime=50%, Near-prime=30%, Sub-prime=20%)
=== Test 5: Boundary Injection             ===  PASS  (8 boundary + 992 distribution rows)
=== Test 6: Determinism                    ===  PASS  (MD5 hashes identical)

============================================================
  All Phase 4+5 tests passed!
============================================================
```

---

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| **"Backend not reachable"** in frontend | Ensure backend is running on port 8001: `python run.py` |
| **CORS errors in browser console** | Check `FRONTEND_URL` in `.env` matches your frontend URL |
| **"RESOURCE_EXHAUSTED" from Gemini** | You've hit the Gemini API rate limit. Wait 60 seconds and retry |
| **"Invalid value for dtype 'int64'"** | Fixed in latest version. Ensure you have the latest `data_engine.py` |
| **LLM returns malformed JSON** | The engine has markdown stripping + graceful degradation built in |
| **`pip install` fails** | Ensure you're using the venv: `.\venv\Scripts\Activate.ps1` |
| **Frontend proxy not working** | Check `vite.config.ts` — proxy target should be `http://localhost:8001` |
| **WebSocket not connecting** | Ensure the backend is running before clicking "Approve & Generate" |

---

## 📐 Design Decisions

1. **Stateless Backend**: No database. The frontend holds all configuration state in React. The backend is pure compute — it receives a config, generates data, and returns results. This simplifies deployment and eliminates state synchronization issues.

2. **Global Distribution Pre-Calculation**: Instead of per-chunk ratio allocation (which causes rounding drift), the engine computes exact row targets globally before chunking. Each chunk decrements mutable counters, guaranteeing mathematically perfect final ratios.

3. **Deterministic Seeding**: `SHA-256(config_id)` produces a 31-bit seed for both NumPy's random generator and Faker. Same config → byte-identical CSV every time.

4. **Actor-Critic with Graceful Degradation**: If the LLM fails to produce valid JSON after `MAX_RETRIES`, the system returns a partial config with `requires_manual_review: true` instead of crashing.

5. **Memory-Safe Chunking**: Data is generated in configurable blocks (default 100K rows). Each chunk is appended to disk and freed from memory, enabling generation of multi-million-row datasets.

6. **250ms WebSocket Throttle**: The frontend debounces WebSocket progress updates to prevent DOM thrashing during fast generation.

---

## 📄 License

Private — Internal use only.l