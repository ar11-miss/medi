"""Vercel entrypoint: Vercel looks for a FastAPI instance named `app` in index.py."""
from app.api import app  # noqa: F401
