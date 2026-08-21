"""
Runs automatically before pytest collects any tests (standard pytest
behavior — no plugin required). Sets a placeholder DATABASE_URL so
modules that need config to load (like app.track, which imports app.db)
don't crash during test collection when no real .env exists — e.g. on a
fresh clone, or in CI, before any real database is configured.

Only used if DATABASE_URL isn't already set — a real local .env still
takes priority, this is purely a fallback.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://placeholder:placeholder@localhost/placeholder")