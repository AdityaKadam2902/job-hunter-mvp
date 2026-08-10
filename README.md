# Job Hunter MVP — Step 2

Local-first, zero-cost job discovery pipeline: Greenhouse + Lever connectors →
normalized job store (Postgres + pgvector) → local embeddings via Ollama.

Matching/scoring/reranking comes in a later step — this step is just:
**get real job data flowing into your own database, correctly.**

## Prerequisites (you already have these)

- Postgres running locally with the `vector` extension enabled
- Ollama running locally with `nomic-embed-text` pulled
- A Groq API key (not used yet — saved for the scoring step)

## Setup

```bash
cd job-hunter-mvp
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env with your real DATABASE_URL, OLLAMA_URL, GROQ_API_KEY
```

### 1. Create the table

```bash
psql "$DATABASE_URL" -f schema.sql
```

This creates the `jobs` table with a `vector(768)` embedding column
(768 = `nomic-embed-text`'s output dimension — if you switch embedding
models later, update this number to match, or inserts will fail).

### 2. Add companies to track

Open `app/companies.py` and fill in real Greenhouse/Lever company slugs.

**How to find a company's slug:**
- Greenhouse: their careers page URL usually looks like
  `boards.greenhouse.io/{slug}` or `job-boards.greenhouse.io/{slug}` — the slug
  is what you put in the list.
- Lever: careers page URL looks like `jobs.lever.co/{slug}`.

I've left the lists empty rather than guessing real company slugs for you —
company/ATS pairings change over time, and a wrong guess here would silently
return zero jobs instead of failing loudly. Pick 3–5 real companies you
actually want to work at, check their careers page URL pattern, and add them.

### 3. Run the ingest pipeline

```bash
python -m app.ingest
```

This will:
1. Fetch open roles from each configured Greenhouse/Lever company
2. Normalize them into one schema
3. Tag a rough seniority level (entry/mid/senior) from the title + description
4. Deduplicate by content hash (same role posted twice won't double-insert)
5. Generate a local embedding via Ollama for each new job
6. Upsert everything into Postgres

Run it again anytime — it's idempotent, only new/changed listings get
re-embedded.

### 4. Sanity check

```bash
psql "$DATABASE_URL" -c "SELECT source, company, title, seniority FROM jobs ORDER BY scraped_at DESC LIMIT 10;"
```

If you see real rows here, step 2 is done. Matching, scoring, and the eval
harness are the next step — don't build those until this is pulling clean
real data.

## What's deliberately NOT in this step

- No LLM calls (Groq key is wired but unused — that's step 3)
- No matching/scoring logic
- No frontend
- No Workday connector (Greenhouse + Lever only, per the scoped MVP)

Keeping this step narrow is intentional — verify the data layer works before
building anything on top of it.
