"""
Extracts skills from a resume using Groq's LLM API — catches skills
mentioned anywhere in the document (project bullets, experience, summary),
not just under a literal 'Skills' heading, and normalizes synonyms
("Postgres" / "PostgreSQL" -> one term) the regex approach couldn't.

Runs once per resume at ingest time, not per match run — the result is
cached in resumes.skills so normal matching never calls the API.
"""

import json

import httpx

from app.config import settings
from app.scoring import extract_resume_skills  # regex fallback

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

_SYSTEM_PROMPT = (
    "You extract technical skills from resumes. Read the entire resume, "
    "including project descriptions and experience bullets, not just a "
    "Skills section if one exists. Return ONLY a JSON array of lowercase "
    "skill strings — no explanation, no markdown code fences, no keys, "
    "just the array. Normalize obvious synonyms to one form (e.g. "
    "'PostgreSQL' and 'Postgres' both become 'postgresql'). Include "
    "languages, frameworks, libraries, databases, cloud/infra tools, and "
    "named techniques (e.g. 'rag', 'hybrid search', 'fine-tuning'). Do not "
    "include soft skills, job titles, or company names."
)


def extract_skills_llm(resume_text: str) -> list[str]:
    """Returns a normalized skill list, or falls back to regex extraction
    if the Groq API key is missing or the call fails for any reason —
    ingest should never hard-fail just because skill extraction had a
    hiccup."""
    if not settings.groq_api_key:
        print("[skills] no GROQ_API_KEY set — falling back to regex extraction")
        return sorted(extract_resume_skills(resume_text))

    try:
        resp = httpx.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": resume_text[:8000]},
                ],
                "temperature": 0,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()

        # Model sometimes wraps output in ```json fences despite instructions —
        # strip those before parsing rather than failing on them.
        if content.startswith("```"):
            content = content.strip("`")
            content = content.removeprefix("json").strip()

        skills = json.loads(content)
        if not isinstance(skills, list):
            raise ValueError(f"expected a JSON array, got {type(skills)}")

        cleaned = sorted({str(s).strip().lower() for s in skills if str(s).strip()})
        if not cleaned:
            raise ValueError("LLM returned an empty skill list")
        return cleaned

    except Exception as e:
        print(f"[skills] LLM extraction failed ({e}) — falling back to regex extraction")
        return sorted(extract_resume_skills(resume_text))