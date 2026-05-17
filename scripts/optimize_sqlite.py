"""Run SQLite optimization steps: PRAGMA settings, ANALYZE, and PRAGMA optimize.

Usage:
    python3 scripts/optimize_sqlite.py

This script uses the project's DB path via `backend.utils.db.get_db_path()`.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any

from backend.utils import db as db_utils


def run() -> int:
    db_path: Path = db_utils.get_db_path()
    print("DB path:", db_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        cur = conn.cursor()

        # Report some PRAGMA values
        pragmas = [
            "journal_mode",
            "synchronous",
            "temp_store",
            "cache_size",
            "page_size",
            "foreign_keys",
        ]
        print("Current PRAGMAs:")
        for p in pragmas:
            try:
                cur.execute(f"PRAGMA {p};")
                v = cur.fetchone()
                print(f"  {p}: {v[0] if v else None}")
            except Exception as e:
                print(f"  {p}: <error> {e}")

        print("\nRunning ANALYZE...")
        cur.execute("ANALYZE;")
        conn.commit()

        print("Running PRAGMA optimize...")
        try:
            cur.execute("PRAGMA optimize;")
        except Exception as e:
            print("PRAGMA optimize not supported on this SQLite build:", e)

        print("\nListing indexes from sqlite_master:")
        cur.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index' ORDER BY tbl_name, name")
        rows = cur.fetchall()
        if not rows:
            print("  (no indexes found)")
        else:
            for r in rows:
                name = r["name"]
                tbl = r["tbl_name"]
                sql = r["sql"]
                print(f"  {tbl} -> {name} -> {('user-defined' if sql else 'implicit')}")

        print("\nTables and their indexes (PRAGMA index_list):")
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [r[0] for r in cur.fetchall()]
        for t in tables:
            try:
                cur.execute(f"PRAGMA index_list('{t}');")
                idxs = cur.fetchall()
                if not idxs:
                    print(f"  {t}: (no indexes)")
                    continue
                print(f"  {t}:")
                for idx in idxs:
                    idxname = idx['name']
                    unique = bool(idx['unique'])
                    print(f"    - {idxname} (unique={unique})")
            except Exception as e:
                print(f"  {t}: <error> {e}")

        print("\nRunning PRAGMA integrity_check...")
        try:
            cur.execute("PRAGMA integrity_check;")
            res = cur.fetchone()
            print("  integrity_check:", res[0] if res else "<no-result>")
        except Exception as e:
            print("  integrity_check error:", e)

        print("\nOptimization complete.")
        return 0

    finally:
        conn.close()


if __name__ == '__main__':
    raise SystemExit(run())
