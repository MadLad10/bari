"""Vercel entrypoint: serves the FastAPI backend as a Python function under /api/*.

The backend lives in backend/ (also run with Docker locally); this file only puts it on the import path.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from main import app  # noqa: E402,F401  (Vercel looks for an ASGI `app`)
