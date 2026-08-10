import httpx

from app.config import settings


def _call_embed_api(text: str) -> list[float]:
    """Uses the newer /api/embed endpoint (not the older /api/embeddings) —
    it handles server-side truncation more gracefully and is less prone to
    500s on long or mixed-unicode input."""
    resp = httpx.post(
        f"{settings.ollama_url}/api/embed",
        json={"model": settings.ollama_embed_model, "input": text, "truncate": True},
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["embeddings"][0]


def embed_text(text: str) -> list[float]:
    """Call local Ollama for an embedding, with a fallback retry on shorter
    text if the first attempt 500s. Some job descriptions (very long, or
    with dense non-Latin unicode) can push past the model's context window
    in ways server-side truncation doesn't always catch cleanly."""
    truncated = text[:4000]

    try:
        vector = _call_embed_api(truncated)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 500:
            # Retry once with a much shorter, ASCII-safe slice before giving up.
            short = truncated.encode("ascii", errors="ignore").decode()[:800]
            vector = _call_embed_api(short)
        else:
            raise

    if len(vector) != settings.embedding_dim:
        raise ValueError(
            f"Embedding dim mismatch: got {len(vector)}, expected {settings.embedding_dim}. "
            f"Check EMBEDDING_DIM in .env matches your Ollama model's real output size."
        )
    return vector