"""
Run with: python -m app.resume_ingest

Reads every .pdf / .docx / .txt file from the resumes/ folder, extracts text,
embeds it with the same local Ollama model used for jobs, and stores it in
the `resumes` table. This is the dynamic counterpart to hardcoding your
resume text — drop a new file in the folder and re-run, no code changes.

File naming convention: name your files by version, e.g.
  resumes/ai-ml-focused.pdf
  resumes/backend-focused.pdf
The filename (minus extension) becomes the version_label.
"""

import hashlib
import sys
from pathlib import Path

from app.db import get_raw_conn
from app.embeddings import embed_text
from app.llm_extract import extract_skills_llm

RESUME_DIR = Path("resumes")


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()

    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            sys.exit("pypdf not installed — run: pip install pypdf")
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if suffix == ".docx":
        try:
            import docx
        except ImportError:
            sys.exit("python-docx not installed — run: pip install python-docx")
        d = docx.Document(str(path))
        return "\n".join(p.text for p in d.paragraphs)

    raise ValueError(f"Unsupported resume file type: {suffix} (use .pdf, .docx, or .txt)")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def main() -> None:
    if not RESUME_DIR.exists():
        RESUME_DIR.mkdir()
        print(f"Created {RESUME_DIR}/ — drop your resume file(s) in there and re-run this.")
        return

    files = [f for f in RESUME_DIR.iterdir() if f.suffix.lower() in (".pdf", ".docx", ".txt")]
    if not files:
        print(f"No resume files found in {RESUME_DIR}/ — add a .pdf, .docx, or .txt file and re-run.")
        return

    conn = get_raw_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT content_hash FROM resumes")
            existing = {row[0] for row in cur.fetchall()}

        for path in files:
            text = extract_text(path).strip()
            if not text:
                print(f"[resume] '{path.name}' extracted empty text — skipping. Check the file isn't a scanned image PDF.")
                continue

            h = content_hash(text)
            version_label = path.stem

            if h in existing:
                print(f"[resume] '{path.name}' unchanged since last run — skipping re-embed.")
                continue

            print(f"[resume] embedding '{path.name}' as version '{version_label}'...")
            vector = embed_text(text)

            print(f"[resume] extracting skills via Groq for '{version_label}'...")
            skills = extract_skills_llm(text)
            print(f"[resume] extracted {len(skills)} skills: {', '.join(skills)}")

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO resumes (filename, version_label, raw_text, content_hash, embedding, skills)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (content_hash) DO NOTHING
                    """,
                    (path.name, version_label, text, h, vector, skills),
                )
            conn.commit()
            print(f"[resume] stored '{version_label}' ({len(text)} chars)")

    finally:
        conn.close()

    print("Done.")


if __name__ == "__main__":
    main()