# BRAHMO Rules Engine + Supra Hospital AI Assistant

A two-part system built for Supra Multi-Specialty Hospital, Hyderabad:

1. **BRAHMO Rules Engine** — a BFS Traversal + 5-Check Filter Pipeline that takes 50 organizational knowledge nodes and filters them down to the exact authorized subset for a specific user. Zero LLM used in this pipeline.

2. **Supra Hospital AI Assistant** — a clinical chat interface that uses the BRAHMO pipeline to retrieve the right knowledge nodes for the active doctor, injects them as context into an LLM, and returns Supra-specific answers. Shows a side-by-side comparison with raw ChatGPT to demonstrate the difference.

---

## What Makes This Different From Just Using ChatGPT

| Question | Raw ChatGPT | Supra Hospital AI |
|---|---|---|
| "Post-TKR pain medication?" | "NSAIDs for inflammation..." | "Paracetamol 650mg QDS first-line per Dr. Vikram Jan 2025. AVOID NSAIDs — surgical bleeding risk." |
| "Patient Rajan knee pain?" | "Ibuprofen or diclofenac..." | "ABSOLUTE contraindication: No NSAIDs for Rajan. Warfarin + GI bleed 2024. Paracetamol ONLY." |
| "Our sepsis protocol?" | "Sepsis-3 bundle..." | "Supra Sepsis Bundle v3 2026: lactate within 1 HOUR (tightened from v2's 3 hours)." |
| "Mrs. Padma's medications?" | "Cannot provide patient info" | "Padma, 62F, Type 2 DM. Ekadashi fasting: skip Glimepiride, continue Metformin. 3 hypoglycemia episodes 2025." |

ChatGPT's answer for Rajan would cause a life-threatening GI bleed. The BRAHMO pipeline ensures the LLM only sees verified, access-controlled, org-specific knowledge.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.9+ + FastAPI + Uvicorn |
| Database | Supabase (PostgreSQL) |
| Frontend | Next.js 14 + React + Tailwind CSS |
| AI (optional) | OpenAI GPT-4o-mini |

---

## Quick Start

> **Prerequisites:** Python 3.9+, Node.js 18+, a free [Supabase](https://supabase.com) account.

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
5. Go to **Settings → API** and note your **Project URL** and **anon key**.

### 3. Backend (Python / FastAPI)

```bash
# From the repo root
python3 -m venv venv
source venv/bin/activate        # Windows: .\venv\Scripts\Activate.ps1

pip install -r backend/requirements.txt

# Copy the example env file and fill in your credentials
cp .env.example .env
```

Open `.env` and set:

```env
SUPABASE_URL=https://<your-project-ref>.supabase.co
SUPABASE_KEY=<your-anon-key>

# Optional — only needed for the Hospital AI Assistant chat feature
# Without this, the pipeline still runs and context nodes are shown,
# but no LLM response will be generated.
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
```

```bash
uvicorn backend.main:app --reload --port 8000
```

- API: http://localhost:8000
- Swagger docs: http://localhost:8000/docs

### 4. Frontend (Next.js)

```bash
cd frontend

npm install

cp .env.local.example .env.local
# Open .env.local and set:
#   NEXT_PUBLIC_SUPABASE_URL=https://<your-project-ref>.supabase.co
#   NEXT_PUBLIC_SUPABASE_ANON_KEY=<your-anon-key>
#   NEXT_PUBLIC_API_URL=http://localhost:8000

npm run dev
```

> ⚠️ **Never commit `.env` or `.env.local`** — both are git-ignored. Use the `.example` files as templates only.

- **BRAHMO Rules Engine:** http://localhost:3000
- **Hospital AI Assistant:** http://localhost:3000/ai

---

## Running Tests

```bash
# From the repo root
source venv/bin/activate
python -m pytest backend/tests/ -v
# → 219 passed
```

---

## API Endpoints

### BRAHMO Rules Engine

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/users` | List all active users |
| `POST` | `/pipeline/{user_id}` | Run full BFS + 5-check pipeline for one user |
| `POST` | `/pipeline/compare` | Run pipeline for multiple users side-by-side (body: `{"user_ids": [...]}`) |

### Hospital AI Assistant

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/ai/users` | List all active users (for chat UI) |
| `POST` | `/ai/chat` | Context-aware chat: runs BRAHMO pipeline → injects nodes → calls LLM (body: `{"user_id": "U-PRIYA", "query": "..."}`) |
| `POST` | `/ai/chat/raw` | Raw chat with zero Supra context — for side-by-side comparison (body: `{"query": "..."}`) |

### Example: Run pipeline for Nurse Priya

```bash
curl -X POST http://localhost:8000/pipeline/U-PRIYA
```

### Example: Ask the AI assistant as Dr. Vikram

```bash
curl -X POST http://localhost:8000/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "U-VIKRAM", "query": "What pain medication for a post-TKR patient?"}'
```

---

## BRAHMO Pipeline Architecture

See [`docs/architecture.md`](docs/architecture.md) for full design rationale.
See [`docs/supra-ai-design-document.md`](docs/supra-ai-design-document.md) for the Hospital AI Assistant design document.

```
User opens session
  → Permission Compiler     compile O(1) {level: can_read, can_write} dict
  → Entry Point Resolver    map dept → DAG leaf node
  → BFS Traversal           walk upward from entry, visited set, multi-parent safe
  → Zone 2 Injector         add all GLOBAL nodes (hospital-wide safety rules)
  → Check 1: Isolation      WHERE org_id = user.org_id
  → Check 2: Compliance     WHERE NOT (compliance_tags NOT IN user.clearance)
  → Check 3: Permission     WHERE hierarchy_level >= user.ceiling  (O(1) lookup)
  → Check 4: Temporal       WHERE status != SUPERSEDED AND valid_until > NOW
  → Check 5: Derivability   WHERE derivability_score < 0.7
  → Candidate Set Assembler annotate with type, importance, distance, compression_hint
```

### For the AI Assistant, after the pipeline:

```
Candidate nodes (10-22 nodes)
  → Sort: CONSTRAINT → ANTI_PATTERN → DECISION → FACT, then by importance desc
  → Build system prompt with Supra knowledge context
  → Call LLM (GPT-4o-mini, temperature 0.2)
  → Return answer + context_nodes_used + pipeline_ms + llm_ms
```

---

## Expected Pipeline Results

| User | Role | Dept | Ceiling | Final Candidates |
|------|------|------|:-------:|:----------------:|
| Nurse Priya | VIEWER | ortho | L10 | ~15 |
| Dr. Vikram | HOD | ortho | L4 | ~22 |
| Dr. Ananya | EDITOR | medicine | L8 | ~16 |
| Dr. Sharma | HOD | medicine | L4 | ~20 |
| Pharmacist Ravi | VIEWER | pharmacy | L12 | ~10 |
| Dr. Sunita (QA) | QUALITY | quality | L6 | ~18 |
| Admin Suresh | ADMIN | admin | L1 | ~40 |

Key invariants verified by the test suite:
- Priya sees **zero** Cardiology / Paediatrics / ICU nodes
- Priya sees **zero** MNPI-tagged nodes (no compliance clearance)
- Priya sees **zero** SUPERSEDED nodes (Sepsis v2 excluded)
- Vikram sees the ortho budget (MNPI) but **not** the vendor negotiation strategy (MNPI+CONFIDENTIAL)
- Suresh sees everything including all MNPI+CONFIDENTIAL nodes

---

## Project Structure

```
brahmo-rules-engine/
├── .env.example                   ← copy to .env, fill in credentials
├── README.md
├── docs/
│   ├── architecture.md            ← BRAHMO pipeline design rationale
│   └── supra-ai-design-document.md← 10-page Hospital AI Assistant design doc
├── supabase/
│   ├── schema.sql                 ← run first in Supabase SQL Editor
│   └── seed.sql                   ← run second (50 nodes + 7 users + edges)
├── backend/
│   ├── main.py                    ← FastAPI app (BRAHMO + AI routes)
│   ├── ai_assistant.py            ← Hospital AI Assistant endpoints
│   ├── requirements.txt
│   ├── pipeline/
│   │   ├── permission_compiler.py ← O(1) permission lookup builder
│   │   ├── entry_point_resolver.py← dept → DAG entry point
│   │   ├── bfs_traversal.py       ← upward BFS with visited set
│   │   ├── zone2_injector.py      ← inject GLOBAL nodes after BFS
│   │   ├── five_check_filter.py   ← 5 sequential checks
│   │   └── candidate_assembler.py ← annotate + sort final nodes
│   ├── models/
│   │   ├── user.py
│   │   ├── node.py
│   │   └── candidate_set.py
│   └── tests/                     ← 219 tests, all passing
│       ├── test_bfs.py
│       ├── test_bfs_hardened.py
│       ├── test_five_checks.py
│       ├── test_five_checks_hardened.py
│       ├── test_permission_compiler.py
│       ├── test_assembler_and_zone2.py
│       ├── test_document_requirements.py
│       ├── test_gap_coverage.py
│       └── test_pipeline.py
└── frontend/
    └── src/
        ├── app/
        │   ├── page.tsx           ← BRAHMO Rules Engine UI (/)
        │   └── ai/
        │       └── page.tsx       ← Hospital AI Assistant UI (/ai)
        ├── components/
        │   ├── FilterFunnel.tsx
        │   ├── DAGViewer.tsx
        │   ├── CandidateSet.tsx
        │   ├── CandidateTable.tsx
        │   ├── ComparisonView.tsx
        │   ├── TimingDisplay.tsx
        │   └── UserSelector.tsx
        └── lib/
            ├── supabase.ts
            └── types.ts
```

---

## The 5 Assessment Test Queries

These queries are pre-loaded as quick-send buttons in the AI assistant UI at `/ai`:

1. `"What pain medication should I give a post-TKR patient?"`
2. `"Patient Rajan has knee pain, what should I prescribe?"`
3. `"When should I start DVT prophylaxis after surgery?"`
4. `"What's our sepsis protocol?"`
5. `"Tell me about Mrs. Padma's medication management"`

Each shows both the Supra-aware AI answer and the raw ChatGPT answer side-by-side.

---

## Without an OpenAI API Key

The BRAHMO Rules Engine works fully without any API key — all 219 tests pass, the pipeline runs, and the filter funnel visualization works. For the AI assistant (`/ai`), the backend will return a message confirming the pipeline ran and listing which context nodes were retrieved, but the LLM response will not be generated. Add `OPENAI_API_KEY=sk-...` to `.env` when ready to enable it.
