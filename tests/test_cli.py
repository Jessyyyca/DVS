"""CLI smoke tests (no network, no DB)."""

from __future__ import annotations

import io
import sys

import pytest

from dvs.cli import main as cli_main
from dvs.schema import read_schema


def test_schema_loads() -> None:
    sql = read_schema()
    assert sql.startswith("--")
    assert "CREATE TABLE" in sql


def test_generate_sql_writes_to_stdout(capsys) -> None:
    cli_main(["generate-sql"])
    out = capsys.readouterr().out
    assert "CREATE TABLE" in out
    assert "BEGIN" in out
    assert "COMMIT" in out


def test_generate_sql_with_out_file(tmp_path) -> None:
    target = tmp_path / "schema.sql"
    cli_main(["generate-sql", "--out", str(target)])
    assert target.exists()
    body = target.read_text(encoding="utf-8")
    assert "CREATE TABLE" in body
    assert "DROP TABLE IF EXISTS daily_price" in body


def test_generate_sql_does_not_touch_db(monkeypatch) -> None:
    """generate-sql must not import db or open a pool."""
    from dvs import db as db_module

    calls = {"get_pool": 0, "close_pool": 0}
    monkeypatch.setattr(
        db_module, "get_pool", lambda *a, **kw: calls.__setitem__("get_pool", 1)
    )
    monkeypatch.setattr(
        db_module,
        "close_pool",
        lambda *a, **kw: calls.__setitem__("close_pool", 1),
    )
    cli_main(["generate-sql"])
    assert calls["get_pool"] == 0
    assert calls["close_pool"] == 0


def test_help_lists_text() -> None:
    """argparse --help should mention every subcommand."""
    import argparse

    parser = argparse.ArgumentParser(prog="dvs")
    sub = parser.add_subparsers(dest="api", required=True)
    for name in (
        "limitless",
        "tickermint-products",
        "tickermint-prices",
        "generate-sql",
    ):
        sub.add_parser(name)

    # Sanity: build_parser in cli.py exposes all four.
    from dvs.cli import _build_parser

    actions = {
        a.dest
        for a in _build_parser()._actions
        if isinstance(a, argparse._SubParsersAction)
    }
    assert {"limitless", "tickermint-products", "tickermint-prices", "generate-sql"} <= {
        s for s in _build_parser()._subparsers._group_actions[0].choices
    }