"""Load the database DSN from environment or .env file."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)


def get_dsn(env_var: str = "DVS_DB_DSN") -> str:
    """Return the DSN from the environment, or exit with a clear message."""
    dsn = os.environ.get(env_var)
    if not dsn:
        raise SystemExit(
            f"Set {env_var} in env or in {_ENV_PATH} (see .env.example)."
        )
    return dsn