"""Schema constants for DDL bootstrap and migration generation."""

from __future__ import annotations

import pathlib

SCHEMA_PATH = pathlib.Path(__file__).resolve().parent / "schema.sql"


def read_schema() -> str:
    """Return the contents of schema.sql as a single string."""
    return SCHEMA_PATH.read_text(encoding="utf-8")


__all__ = ["read_schema", "SCHEMA_PATH"]