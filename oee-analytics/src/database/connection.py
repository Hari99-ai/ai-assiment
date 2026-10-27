import sqlite3
from pathlib import Path

def initialize(path: Path, schema: Path) -> sqlite3.Connection:
    conn=sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(schema.read_text(encoding="utf-8"))
    return conn
