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

> **Prerequisites:** Python 3.11+, Node.js 18+, a free [Supabase](https://supabase.com) account.

### 1. Clone the repo

```bash
git clone https://github.com/nithinmkannal/BRAHMO-Rules-Engine.git
cd BRAHMO-Rules-Engine
```

### 2. Supabase Setup

1. Create a free project at [supabase.com](https://supabase.com)
2. Go to **SQL Editor** → paste and run `supabase/schema.sql`
3. Go to **SQL Editor** → paste and run `supabase/seed.sql`
4. Verify data:
   ```sql
   SELECT COUNT(*) FROM knowledge_nodes;  -- expect 50
   SELECT COUNT(*) FROM users;            -- expect 7
   ```
5. Go to **Settings → API** and note your **Project URL** and **anon / publishable key** — you'll need them in steps 3 and 4 below.

### 3. Backend (Python / FastAPI)

```bash
# From the repo root
python3 -m venv venv
source venv/bin/activate        # Windows: .\venv\Scripts\Activate.ps1

pip install -r backend/requirements.txt

# Copy the example env file and fill in your Supabase credentials
cp .env.example .env
# Open .env and set:
#   SUPABASE_URL=https://<your-project-ref>.supabase.co
#   SUPABASE_KEY=<your-anon-key>

uvicorn backend.main:app --reload --port 8000
```

- API: http://localhost:8000
- Swagger docs: http://localhost:8000/docs

### 4. Frontend (Next.js)

```bash
cd frontend

npm install

# Copy the example env file and fill in your Supabase credentials
cp .env.local.example .env.local
# Open .env.local and set:
#   NEXT_PUBLIC_SUPABASE_URL=https://<your-project-ref>.supabase.co
#   NEXT_PUBLIC_SUPABASE_ANON_KEY=<your-anon-key>
#   NEXT_PUBLIC_API_URL=http://localhost:8000

npm run dev
```

> ⚠️ **Never commit `.env` or `.env.local`** — both are git-ignored. Use the `.example` files as templates only.

- Frontend: http://localhost:3000

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
