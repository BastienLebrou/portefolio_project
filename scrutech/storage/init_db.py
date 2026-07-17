"""Create (or upgrade) the central ScruTech DuckDB store, then report what's inside.

Idempotent: safe to re-run — every table is CREATE ... IF NOT EXISTS, so this both
bootstraps a fresh store and applies new tables to an existing one.

Run:  python scrutech/storage/init_db.py
Env:  SCRUTECH_DATA=<dir>   (default: scrutech/data/)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make ``core`` importable when run straight from the repo (no install needed).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core" / "src"))
from core.db import connect  # noqa: E402
from core.storage import data_root, db_path  # noqa: E402


def main() -> int:
    print(f"Store root : {data_root()}")
    print(f"DuckDB     : {db_path()}")
    con = connect()
    try:
        rows = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()
        print(f"\n{len(rows)} tables:")
        for (name,) in rows:
            n = con.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
            print(f"  {name:<22} {n:>8} rows")
        spatial = con.execute(
            "SELECT count(*) FROM duckdb_extensions() WHERE extension_name='spatial' AND loaded"
        ).fetchone()[0]
        print(f"\nspatial extension loaded: {'yes' if spatial else 'no'}")
    finally:
        con.close()
    print("\nOK — store ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
