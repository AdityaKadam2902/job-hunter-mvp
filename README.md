# Job Hunter MVP

A local-first, zero-cost job discovery and matching pipeline built for a
single real use case: surface AI/ML engineering roles I'm actually
competitive for, ranked by genuine fit — not a generic keyword search.

**Current state: Precision@20 = 1.00** on a held-out labeled sample (n=19).
That number didn't come easy — the "Engineering Decisions" section below is
a real account of the bugs that got in the way and how they were found and
fixed, because that process is honestly the most interesting part of this
project.

## Architecture

```
Sources (4)              Storage                Matching                Output
─────────────            ─────────              ──────────               ──────
Greenhouse    ─┐
Lever         ─┤          Postgres +             Hybrid score:            Ranked list
RemoteOK      ─┼─ Ingest → pgvector    → Match →  similarity +      →     + eval CSV
Ashby         ─┘          job store              keyword overlap +
                                                  seniority fit +
Resume (PDF/DOCX)                                domain fit +
  → Ollama embedding                             AI-specificity
  → Groq skill extraction
```

- **Discovery**: Greenhouse and Lever connectors hit each company's public
  ATS API directly (no scraping). RemoteOK is a tag-based aggregator — one
  call covers many companies with zero per-company maintenance. Ashby adds
  a fourth, same pattern as Greenhouse/Lever.
- **Storage**: local Postgres with the `pgvector` extension. Every job and
  resume gets embedded locally via Ollama (`nomic-embed-text`, 768 dims) —
  no embedding API cost or rate limit.
- **Resume parsing**: dynamic, not hardcoded. Drop a resume file in
  `resumes/`, and Groq extracts skills from the *entire* document (project
  bullets included, not just a Skills heading) into a cached, reusable list.
- **Matching**: pgvector cosine similarity narrows ~800 jobs to a top-100
  shortlist, then a five-factor deterministic rubric scores each one:
  semantic similarity, keyword overlap, seniority fit, domain fit, and
  AI-specificity. Every factor is visible in the output — no black-box score.
- **Eval harness**: every match run writes a full CSV. Manually labeling a
  sample against the ranking gives Precision@10/@20 — a real number instead
  of eyeballing whether a change helped.

## Setup

```bash
cd job-hunter-mvp
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env with your real DATABASE_URL, OLLAMA_URL, GROQ_API_KEY
```

**Prerequisites:** Postgres with `pgvector` enabled, Ollama with
`nomic-embed-text` pulled, a free Groq API key.

```bash
psql "$DATABASE_URL" -f schema.sql          # creates jobs + resumes tables
```

Add real company slugs to `app/companies.py` (Greenhouse/Lever/Ashby) and
tags to `REMOTEOK_TAGS` — see comments in that file for how to find a
company's slug from their careers page URL.

```bash
python -m app.ingest              # fetch + normalize + embed + store jobs
python -m app.resume_ingest       # drop a resume in resumes/ first
python -m app.match               # rank jobs against your resume
python -m app.auto_label          # optional: speeds up labeling
python -m app.eval                # precision numbers, after labeling
```

## Regression tests

```bash
pytest tests/
```

Every bug in the "Engineering decisions" section below has a permanent
test in `tests/` — not a one-time manual check. A GitHub Actions workflow
(`.github/workflows/tests.yml`) runs the full suite automatically on every
push, so a future edit that reintroduces one of these bugs fails a check
immediately instead of shipping silently and needing to be re-discovered
by eye, the way each one originally was.

## Engineering decisions — the real bug history

Four real scoring bugs were found and fixed through the eval harness, not
by eyeballing output. Each one moved the measured precision.

**1. Seniority mis-tagging from an overly broad regex.**
The entry-level classifier matched the bare word "associate," which fired
on non-technical titles like "Business Operations Associate" just as much
as genuine junior engineering roles — pushing irrelevant business roles to
the top purely on a false seniority tag. Fixed by removing the bare match
and requiring more specific entry-level language.

**2. Keyword score diluted by vocabulary size.**
`keyword_overlap` was originally `matched / total_resume_skills`. Once
resume parsing improved from ~15 keywords to 51 real, LLM-extracted ones,
a genuinely strong match (7 real skills matched) scored as low as `0.14`,
because it was being divided by 51. Fixed by switching to an absolute
count with a saturation cap (`min(1.0, matched / 6)`), so a deep, specific
skillset stops being penalized for its own size.

**3. Substring false positives in keyword matching.**
Plain `in` string checks let short skill terms match inside unrelated
words — "agno" (a real skill, an agent framework) was matching inside
"diagnostics" on every Wayve (autonomous vehicle) listing; "rag" was
matching inside "storage" almost everywhere. Fixed with word-boundary
regex matching instead of substring containment.

**4. No domain-fit or AI-specificity signal — the big one.**
The rubric had no concept of "wrong department" or "wrong specialization."
A Legal/Compliance role scored `0.51` because its description happened to
mention "RAG" once; a generic Backend/DevOps role scored identically to an
actual ML Engineer role at the same AI-native company, because the
company's own boilerplate ("Abnormal AI is...") polluted every job
description regardless of role. Fixed by adding two new dimensions —
`domain_fit` (penalizes non-technical departments) and `ai_specificity`
(distinguishes core AI/ML roles from generic SWE, checked on **title
only**, since description text is unreliable at AI-native companies).

**Measured result of fix #4:** Precision@20 went from **0.78 → 1.00** on
the same labeled methodology, with zero remaining score/label
disagreements. That's the number that actually validates the fix — not
just "the list looks better."

**5. `engagement_type` silently hardcoded to always be "full_time".**
Every job, regardless of source, was tagged full-time by default with no
actual classification logic — meaning genuine freelance/contract listings
(which started appearing once RemoteOK was added, e.g. "LLM Engineer
Freelancer," "Software Integration Engineer (6 months Contract)") were
scored and displayed as if they were full-time roles. Fixed with a
title-based classifier, same pattern and same title-over-description
reasoning as the seniority/domain classifiers above.

**Lesson that generalizes across all five bugs:** short substrings and
full description text are both unreliable signals in this domain — company
boilerplate and incidental word matches pollute them in predictable ways.
Titles and word-boundary-matched keywords are far more trustworthy.

## Known limitations (honest, not fixed yet)

- Some high-demand RemoteOK listings gate the actual "Apply" action behind
  a sign-up/subscription prompt. RemoteOK is treated purely as a
  **discovery** source here, not a guaranteed one-click apply path the way
  Greenhouse/Lever/Ashby are — when a strong match traces back to a known
  company, applying via that company's own career page directly is
  preferred anyway, consistent with the project's "direct portal beats
  aggregator" priority.
- Workday isn't covered (no clean public API the way Greenhouse/Lever/Ashby
  have) — a real coverage gap for larger enterprises.
- The eval labeled sample (n=19) is still small. Precision@20=1.00 is a
  real, promising number, not yet a statistically bulletproof one.
- No auto-apply — by design. Application forms get reviewed by a human
  before submission, not blindly automated.
- No tracking/CRM layer yet for what happens after a match (applied,
  interview, outcome) — planned, not built.

## Roadmap (not built, deliberately deferred)

- Resume-tailoring suggestions per job (Groq, reusing the same skill
  extraction infrastructure)
- Application tracking workspace (CareerVault-style entity model:
  opportunity → application → resume version → interview → outcome)
- Scheduled daily runs (GitHub Actions, free tier)
- Freelance/contract engagement-type handling done properly