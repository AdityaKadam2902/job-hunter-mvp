from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pgvector.psycopg2 import register_vector
import psycopg2

from app.config import settings

engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def get_raw_conn():
    """Raw psycopg2 connection with pgvector adapter registered.
    Used for the upsert path since it's simpler than mapping vector(768)
    through the SQLAlchemy ORM layer for a single-table MVP.
    """
    conn = psycopg2.connect(settings.database_url.replace("postgresql+psycopg2://", "postgresql://"))
    register_vector(conn)
    return conn
