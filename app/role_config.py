# Role targeting is now PER-PROFILE, keyed by a resume's version_label —
# selected automatically based on whose resume is being matched, no more
# manually editing this file back and forth between people.
#
# Add a new person by adding a new key here matching their resume's
# version_label (the filename minus extension — see app/resume_ingest.py).
# Anyone whose resume doesn't have an explicit entry falls back to
# "default" below.

ROLE_PROFILES = {
    "default": {
        # Highest "specificity" score — the role family actually being targeted.
        "role_specific_markers": [
            "machine learning", "ml engineer", " ai ", "ai engineer", "genai",
            "generative ai", "applied scientist", "research scientist",
            "data scientist", "nlp", "computer vision", "deep learning",
            "llm", "artificial intelligence",
        ],
        # Real engineering work, just not the specific target — deprioritized,
        # not excluded.
        "generic_adjacent_markers": [
            "backend", "front end", "frontend", "devops", "site reliability",
            "systems engineer", "platform engineer", "integration engineer",
            "qa engineer", "security engineer", "infrastructure",
        ],
        # Fine-grained badges, title-only (company boilerplate pollutes
        # description text at AI-native companies regardless of role).
        "sub_role_tags": {
            "GenAI": ["generative ai", "genai", "llm", "large language model"],
            "Agentic AI": ["agentic", "multi-agent", "ai agent", "agent"],
            "RAG": ["rag", "retrieval augmented", "retrieval-augmented"],
            "MLOps": ["mlops", "ml infrastructure", "model deployment", "ml platform"],
            "Computer Vision": ["computer vision", "cv engineer"],
            "NLP": ["nlp", "natural language processing"],
            "Research": ["research scientist", "applied scientist"],
            "AI/ML Engineer": ["machine learning engineer", "ml engineer", "ai engineer", "applied ai"],
        },
    },

    "Sakshi_Patil_Resume": {
        "role_specific_markers": [
            "data scientist", "data analyst", "data engineer", "analytics engineer",
            "business intelligence", "bi analyst", "reporting analyst",
            "data warehouse", "machine learning",
        ],
        "generic_adjacent_markers": [
            "software engineer", "backend", "frontend", "devops",
            "systems engineer", "qa engineer",
        ],
        "sub_role_tags": {
            "Data Analyst": ["data analyst", "business intelligence", "bi analyst"],
            "Data Engineer": ["data engineer", "etl", "data pipeline"],
            "Data Scientist": ["data scientist"],
            "BI / Reporting": ["power bi", "tableau", "dax", "reporting analyst"],
        },
    },
}

DEFAULT_PROFILE_KEY = "default"


def get_role_profile(version_label: str | None) -> dict:
    """Looks up the role profile for a given resume's version_label,
    falling back to 'default' (currently AI/ML) if that person doesn't
    have an explicit entry yet."""
    return ROLE_PROFILES.get(version_label, ROLE_PROFILES[DEFAULT_PROFILE_KEY])