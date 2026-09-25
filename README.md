# DVS

Fragestellungen:
1. Vergleich der Preise von Pokemonkarten mit Typ und Basestats aus Pokemonspielen
2. Vergleich der Karten-Preise mit Verwendung in Turnieren.
3. Vergleich der Verwendung in Turnieren mit Typ und Basestats aus Pokemonspielen

Quellsysteme:
Daten zu Pokemon: PokeAPI - https://pokeapi.co/
Daten zu Karten-Preisen: TickerMint - https://tickermint.cards/developers
Daten zu Turniern: Limitless - https://docs.limitlesstcg.com/developer.html

## Setup

```sh
uv sync --group dev
cp .env.example .env  # then edit DVS_DB_DSN
```

The DSN is read from `.env` (loaded by `python-dotenv`) or the environment
variable `DVS_DB_DSN`. `.env` is git-ignored.

### Local Postgres via docker compose

```sh
docker compose up -d
export DVS_DB_DSN="postgres://dhw:Bride0-Viable-Outrage@localhost:5433/db?sslmode=disable"
dvs generate-sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U dhw -d db
dvs limitless --from-date 2026-01-01 --test
```

The compose stack uses port `5433` on the host (so it doesn't fight a
system Postgres on 5432) and persists data in the `dvs-pgdata` volume.
`sslmode=disable` is fine inside the trusted network -- never expose
this on a public network without TLS + auth.

## One CLI, five subcommands

All importers share the `ApiImporter` interface (async `run()` method)
and the `RateLimitedMixin` (throttles HTTP calls with a burst window and
optional rolling hour/day caps). Every importer also exposes `async test()`
which probes the API and pings the DB without touching the import tables.
The CLI gains `--test` for the same purpose. `generate-sql` prints the
schema bootstrap SQL for manual migration runs.

```sh
dvs limitless --from-date 2026-01-01 --test   # API + DB reachability
dvs tickermint-products --test
dvs tickermint-prices --test
dvs pokeapi --names ditto,pikachu --test
dvs pokeapi --from-id 1 --to-id 151            # full Gen 1

dvs generate-sql                              # print schema.sql to stdout
dvs generate-sql --out schema.sql            # write to file
dvs generate-sql | docker exec -i postgres-dhw \
                 psql -v ON_ERROR_STOP=1 -U dhw -d db
```

`dvs pokeapi` accepts either `--ids 1,4,7`, `--names ditto,pikachu`, or
`--from-id 1 --to-id 151` (inclusive range). It fills the ERM `pokemon`,
`type`, `ability`, `pokemon_type`, `pokemon_ability` tables. Moves are
intentionally not pulled by default (one Pokemon has 100+ moves); see
`dvs/api/pokeapi.py` if you want them.

## Logging

Every importer, the pool singleton, and the CLI use stdlib `logging`.
By default the CLI configures `logging.basicConfig(level=INFO, format=
"%(asctime)s %(levelname)s %(message)s")`. Pass a custom logger into the
constructor to redirect or silence a specific importer:

```python
import logging
log = logging.getLogger("myapp.dvs")
importer = LimitlessImporter(pool, logger=log)
```

```sh
# 01 - Limitless tournaments -> deck / card / deck_card
dvs limitless --from-date 2026-01-01 --format STANDARD \
              --concurrency 4 --rate-burst 60 --rate-window 60

# 02 - match Limitless cards to TickerMint products
dvs tickermint-products --rematch \
                        --rate-burst 60 --rate-window 60

# 03 - import TickerMint historical prices for matched products
dvs tickermint-prices --from-date 2024-02-01 \
                      --rate-burst 60 --rate-window 60
```

Rate-limit flags (shared across subcommands):

- `--rate-burst N` -- max N requests per `--rate-window` seconds.
- `--rate-window S` -- burst window length (e.g. `60` = per minute, `1` = per second).
- `--max-per-hour N` -- optional rolling-hour cap.
- `--max-per-day N` -- optional rolling-day cap.
- `--concurrency N` -- bounded parallel workers inside one importer.

## Architecture

- `src/dvs/api/base.py` -- `ApiImporter` (ABC, abstract `run()`) + `RateLimitedMixin` + `RateLimit` dataclass.
- `src/dvs/api/limitless.py` -- `LimitlessImporter` (was `01_import_limitless.py`).
- `src/dvs/api/tickermint_products.py` -- `TickermintProductsImporter` (was `02_match_tickermint_products.py`).
- `src/dvs/api/tickermint_prices.py` -- `TickermintPricesImporter` (was `03_import_tickermint_prices.py`).
- `src/dvs/api/pokeapi.py` -- `PokeapiImporter` (fills `pokemon`, `type`, `ability`, and their m:n joins).
- `src/dvs/db.py` -- `asyncpg` pool singleton.
- `src/dvs/config.py` -- `.env` loader, `get_dsn()`.
- `src/dvs/cli.py` -- argparse subcommands -> unified `dvs` console script.
- `src/dvs/schema.sql` -- bootstrap DDL used by `generate-sql` and direct psql runs.
- `src/dvs/pokeapi.py` -- ad-hoc PokeAPI / TickerMint exploration helper.
- `docker-compose.yml` -- local Postgres for development (port 5433).

## Tests

```sh
uv run pytest
```

- `tests/test_base.py` -- rate-limit mixin (no network, no DB).
- `tests/test_limitless_parser.py` and `tests/test_tickermint_matcher.py`
  -- JSON parsers and the conservative candidate matcher.
- `tests/test_idempotency.py` -- each `INSERT` statement runs twice and is
  expected to succeed); covers both ON CONFLICT clauses and the
  try/except `asyncpg.UniqueViolationError` fallback in the card INSERT.
- `tests/test_connection.py` -- `db.ping()` and `ApiImporter.test()` with
  a minimal `aiohttp.ClientSession` stub.
- `tests/_fakepg.py` -- tiny in-memory asyncpg substitute so the
  idempotency tests stay offline.

## Legacy shims

The old top-level `01_import_limitless.py`, `02_match_tickermint_products.py`,
`03_import_tickermint_prices.py`, and `main.py` are kept as thin wrappers
that forward to the new CLI. Remove them once the new workflow is fully
adopted.
