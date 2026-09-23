"""DVS: Pokemon DWH importer (Limitless + TickerMint + PokeAPI)."""

from . import api, cli, config, db

__all__ = ["api", "cli", "config", "db", "main"]


def main() -> None:
    """Console-script entry point."""
    cli.main()
