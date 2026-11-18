"""Database settings. Secrets live in a .env file (never in code, never committed)."""
import os

from dotenv import load_dotenv

load_dotenv()


def database_url() -> str:
    """DATABASE_URL if set, otherwise built from DB_USER / DB_PASSWORD / DB_HOST / DB_PORT / DB_NAME."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "rijalmap_db")
    auth = f"{user}:{password}" if password else user
    return f"postgresql+psycopg2://{auth}@{host}:{port}/{name}"
