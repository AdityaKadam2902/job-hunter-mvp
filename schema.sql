-- Run once: psql "$DATABASE_URL" -f schema.sql

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- where it came from
    source          TEXT NOT NULL,              -- 'greenhouse' | 'lever'
    company         TEXT NOT NULL,
    company_slug    TEXT NOT NULL,               -- the slug used to fetch it
    external_id     TEXT NOT NULL,               -- source's own job id

    -- normalized job fields
    title           TEXT NOT NULL,
    location        TEXT,
    description     TEXT,
    url             TEXT,

    -- classification (rough, rule-based for now — refined in the scoring step)
    engagement_type TEXT NOT NULL DEFAULT 'full_time',   -- full_time | contract | freelance
    seniority       TEXT NOT NULL DEFAULT 'unknown',     -- entry | mid | senior | unknown

    -- dedup + freshness
    content_hash    TEXT NOT NULL UNIQUE,        -- hash of title+company+description
    posted_at       TIMESTAMPTZ,
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- 768 dims = nomic-embed-text output size.
    -- If you switch embedding models later, this MUST match the new model's
    -- output dimension or inserts will fail.
    embedding       vector(768)
);

-- Speeds up "show me new stuff since X" queries during ingest and later dashboards
CREATE INDEX IF NOT EXISTS idx_jobs_scraped_at ON jobs (scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs (company_slug);

-- NOTE: no vector similarity index (ivfflat/hnsw) yet on purpose — those need
-- a meaningful amount of data to tune well, and a wrongly-tuned index is worse
-- than no index at this stage. Add one once you've got a few hundred+ rows
-- and are building the actual matching step.

CREATE TABLE IF NOT EXISTS resumes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename        TEXT NOT NULL,
    version_label   TEXT NOT NULL,           -- e.g. 'ai-ml-focused', 'backend-focused'
    raw_text        TEXT NOT NULL,
    content_hash    TEXT NOT NULL UNIQUE,     -- dedup: re-running won't re-embed an unchanged file
    is_active       BOOLEAN NOT NULL DEFAULT true,
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    embedding       vector(768),
    skills          TEXT[]                    -- LLM-extracted skills, computed once at ingest time
);

-- Safe to re-run: adds the column if you're upgrading an existing resumes
-- table created before this field existed.
ALTER TABLE resumes ADD COLUMN IF NOT EXISTS skills TEXT[];

CREATE TABLE IF NOT EXISTS applications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID NOT NULL REFERENCES jobs(id),
    resume_id       UUID REFERENCES resumes(id),

    -- saved -> applied -> interviewing -> offer / rejected / withdrawn
    status          TEXT NOT NULL DEFAULT 'saved',

    applied_at      TIMESTAMPTZ,
    notes           TEXT,
    follow_up_date  DATE,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- one tracking record per job — re-running 'add' on the same job
    -- updates it rather than creating duplicates
    UNIQUE(job_id)
);

CREATE INDEX IF NOT EXISTS idx_applications_status ON applications (status);