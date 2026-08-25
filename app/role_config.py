# Defines what "highly relevant to my target role" looks like, separate
# from scoring.py's logic. Editing THIS FILE is how you retarget the whole
# matching engine to a different role family — e.g. if you're not
# targeting AI/ML Engineer roles specifically, replace ROLE_SPECIFIC_MARKERS
# below with terms for your actual target (Data Scientist, Data Analyst,
# Data Engineer, etc). No changes to scoring.py needed.
#
# This is also the file to change if you're setting this project up for
# someone else's job search — their own clone, own database, own resume —
# rather than editing scoring.py's logic directly.

# Titles/descriptions containing these score highest on the "specificity"
# dimension — the role family you're actually targeting.
ROLE_SPECIFIC_MARKERS = [
    "machine learning", "ml engineer", " ai ", "ai engineer", "genai",
    "generative ai", "applied scientist", "research scientist",
    "data scientist", "nlp", "computer vision", "deep learning",
    "llm", "artificial intelligence",
]

# Example alternative for a Data Scientist / Data Analyst / Data Engineer
# target — uncomment and use instead of the AI/ML list above:
#
# ROLE_SPECIFIC_MARKERS = [
#     "data scientist", "data analyst", "data engineer", "analytics engineer",
#     "business intelligence", "bi analyst", "sql", "etl", "data pipeline",
#     "tableau", "power bi", "looker", "data warehouse", "dbt",
# ]

# Titles that are real engineering work, just NOT your specific target —
# deprioritized relative to a specific-marker match, but not excluded
# entirely (still legitimate, applicable roles).
GENERIC_ADJACENT_TITLE_MARKERS = [
    "backend", "front end", "frontend", "devops", "site reliability",
    "systems engineer", "platform engineer", "integration engineer",
    "qa engineer", "security engineer", "infrastructure",
]

# Fine-grained badges shown per job in the dashboard — e.g. distinguishing
# "GenAI" from "Agentic AI" from "RAG" within your broader AI/ML target.
# Checked against the TITLE ONLY (not description) — the same lesson from
# fixing ai_specificity_score: company boilerplate at AI-native companies
# mentions AI/GenAI/etc regardless of the actual role, so description text
# is an unreliable signal here. A job can match multiple tags, or none.
SUB_ROLE_TAGS = {
    "GenAI": ["generative ai", "genai", "llm", "large language model"],
    "Agentic AI": ["agentic", "multi-agent", "ai agent", "agent"],
    "RAG": ["rag", "retrieval augmented", "retrieval-augmented"],
    "MLOps": ["mlops", "ml infrastructure", "model deployment", "ml platform"],
    "Computer Vision": ["computer vision", "cv engineer"],
    "NLP": ["nlp", "natural language processing"],
    "Research": ["research scientist", "applied scientist"],
    "AI/ML Engineer": ["machine learning engineer", "ml engineer", "ai engineer", "applied ai"],
}

# Example alternate SUB_ROLE_TAGS for a Data Analyst / BI / Data Engineer
# target (e.g. Sakshi's profile) — swap in on that person's clone instead:
#
# SUB_ROLE_TAGS = {
#     "Data Analyst": ["data analyst", "business intelligence", "bi analyst"],
#     "Data Engineer": ["data engineer", "etl", "data pipeline"],
#     "Data Scientist": ["data scientist"],
#     "BI / Reporting": ["power bi", "tableau", "dax", "reporting analyst"],
# }