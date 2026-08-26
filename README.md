# BRAHMO Rules Engine

A BFS Traversal + 5-Check Filter Pipeline for knowledge graph filtering.
Traverses a DAG of hospital knowledge nodes and applies 5 sequential checks
to produce a personalized, permission-filtered candidate set for a specific user.

**Zero LLM used anywhere in this pipeline.**

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11 + FastAPI + Uvicorn |
| Database | Supabase (PostgreSQL) |
| Frontend | Next.js 14 + React + Tailwind CSS |

---

## Quick Start

### 1. Clone & Setup

```bash
git clone <your-repo>
cd brahmo-rules-engine
```

### 2. Supabase Setup

1. Create a free project at [supabase.com](https://supabase.com)
2. Go to **SQL Editor** → run `supabase/schema.sql`
3. Go to **SQL Editor** → run `supabase/seed.sql`
4. Verify: `SELECT COUNT(*) FROM knowledge_nodes` → should return 50
5. Verify: `SELECT COUNT(*) FROM users` → should return 7
6. Copy your **Project URL** and **anon key** from Settings → API

### 3. Backend (Python / FastAPI)

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate       # Windows: .\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp ../.env.example ../.env
# Edit .env with your Supabase URL and key

# Start server
cd ..
uvicorn backend.main:app --reload --port 8000
```

Backend runs at: http://localhost:8000
API docs at: http://localhost:8000/docs

### 4. Frontend (Next.js)

```bash
cd frontend

# Install dependencies
npm install

# Set environment variables
cp .env.local.example .env.local
# Edit .env.local with your Supabase URL + anon key

# Start dev server
npm run dev
```

Frontend runs at: http://localhost:3000

---

## Running Tests

```bash
cd brahmo-rules-engine
source backend/venv/bin/activate
pytest backend/tests/ -v
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/users` | List all active users |
| `POST` | `/pipeline/{user_id}` | Run full pipeline for one user |
| `POST` | `/pipeline/compare` | Run pipeline for multiple users (body: `{"user_ids": [...]}`) |

### Example: Run pipeline for Nurse Priya

```bash
curl -X POST http://localhost:8000/pipeline/U-PRIYA
```

---

## Pipeline Architecture

See [`docs/architecture.md`](docs/architecture.md) for full design rationale.

```
User → Permission Compiler (O(1) lookup)
     → Entry Point Resolver (dept → DAG leaf node)
     → BFS Traversal (upward, FIFO queue, visited set)
     → Zone 2 Injector (add GLOBAL nodes)
     → Check 1: Isolation (org_id filter)
     → Check 2: Compliance (tag × clearance)
     → Check 3: Permission (O(1) level lookup)
     → Check 4: Temporal (status + valid_until)
     → Check 5: Derivability (score < 0.7)
     → Candidate Set Assembler (annotate + sort)
```

---

## Expected Results

| User | Role | Final Candidates |
|------|------|:-:|
| Nurse Priya | VIEWER L10 | ~15 |
| Dr. Vikram (HOD) | HOD L4 | ~22 |
| Admin Suresh | ADMIN L1 | ~40 |

---

## Project Structure

```
brahmo-rules-engine/
├── .env.example
├── README.md
├── docs/
│   └── architecture.md
├── supabase/
│   ├── schema.sql
│   └── seed.sql
├── backend/
│   ├── main.py                      ← FastAPI app
│   ├── requirements.txt
│   ├── pipeline/
│   │   ├── permission_compiler.py
│   │   ├── entry_point_resolver.py
│   │   ├── bfs_traversal.py
│   │   ├── zone2_injector.py
│   │   ├── five_check_filter.py
│   │   └── candidate_assembler.py
│   ├── models/
│   │   ├── user.py
│   │   ├── node.py
│   │   └── candidate_set.py
│   └── tests/
│       ├── test_bfs.py
│       ├── test_five_checks.py
│       └── test_pipeline.py
└── frontend/
    └── src/
        ├── app/page.tsx
        ├── components/
        │   ├── UserSelector.tsx
        │   ├── FilterFunnel.tsx
        │   ├── TimingDisplay.tsx
        │   ├── CandidateTable.tsx
        │   ├── ComparisonView.tsx
        │   └── DAGViewer.tsx
        └── lib/
            ├── supabase.ts
            └── types.ts
```
