"""Database connection pool (psycopg 3)."""
import os

from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "dbname=water_quality",
)

# Some providers (Heroku, older Railway) emit postgres:// which psycopg 3
# doesn't accept — normalise to postgresql://.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

pool = ConnectionPool(DATABASE_URL, min_size=2, max_size=10, open=False)
