"""SQLite snapshots, durable operation IDs, scoped full-text search, and chat."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .models import Snapshot, now


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "research.sqlite3"
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise RuntimeError("Database is newer than this app. Use the matching app version.")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id TEXT PRIMARY KEY, site_id TEXT NOT NULL, mode TEXT NOT NULL,
                    name TEXT NOT NULL, created TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS site_snapshots ON snapshots(site_id, created);
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY, site_id TEXT NOT NULL, snapshot_id TEXT NOT NULL,
                    role TEXT NOT NULL, content TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS operations (
                    id TEXT PRIMARY KEY, state TEXT NOT NULL, result TEXT, created TEXT NOT NULL);
                CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(
                    snapshot_id UNINDEXED, document_id UNINDEXED, page UNINDEXED, content);
                CREATE TABLE IF NOT EXISTS discovery_catalog (
                    developer TEXT PRIMARY KEY, payload TEXT NOT NULL, updated TEXT NOT NULL);
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, snapshot: Snapshot):
        with self.connect() as db:
            inserted = db.execute(
                "INSERT OR IGNORE INTO snapshots VALUES (?,?,?,?,?,?)",
                (
                    snapshot.id,
                    snapshot.site.id,
                    snapshot.site.mode,
                    snapshot.site.name,
                    snapshot.created,
                    snapshot.model_dump_json(),
                ),
            ).rowcount
            if inserted:
                for doc in snapshot.documents:
                    for page, text in enumerate(doc.pages, 1):
                        db.execute("INSERT INTO passages VALUES (?,?,?,?)", (snapshot.id, doc.id, page, text))

    def load(self, snapshot_id: str) -> Snapshot:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM snapshots WHERE id=?", (snapshot_id,)).fetchone()
        if row is None:
            raise KeyError(snapshot_id)
        return Snapshot.model_validate_json(row[0])

    def list_sites(self, mode: str, query: str = "") -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT id, site_id, name, created FROM (
                SELECT *, row_number() OVER (PARTITION BY site_id ORDER BY created DESC, rowid DESC) AS rn
                FROM snapshots WHERE mode=?) WHERE rn=1 ORDER BY created DESC""",
                (mode,),
            ).fetchall()
        return [dict(row) for row in rows if query.casefold() in row["name"].casefold()]

    def save_discovery(self, developer: str, candidates: list[dict]):
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO discovery_catalog VALUES (?,?,?)",
                (developer, json.dumps(candidates), now()),
            )

    def discovery(self, developer: str) -> list[dict]:
        with self.connect() as db:
            row = db.execute(
                "SELECT payload FROM discovery_catalog WHERE developer=?", (developer,)
            ).fetchone()
        return json.loads(row[0]) if row else []

    def history(self, site_id: str) -> list[dict]:
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT id, created FROM snapshots WHERE site_id=? ORDER BY created DESC, rowid DESC",
                    (site_id,),
                )
            ]

    def messages(self, site_id: str) -> list[dict]:
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute("SELECT * FROM messages WHERE site_id=? ORDER BY rowid", (site_id,))
            ]

    def add_message(self, message_id: str, snapshot: Snapshot, role: str, content: str):
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO messages VALUES (?,?,?,?,?,?)",
                (message_id, snapshot.site.id, snapshot.id, role, content, now()),
            )

    def begin(self, operation_id: str) -> bool:
        with self.connect() as db:
            return bool(
                db.execute(
                    "INSERT OR IGNORE INTO operations VALUES (?,?,?,?)",
                    (operation_id, "running", None, now()),
                ).rowcount
            )

    def finish(self, operation_id: str, state: str, result: str = ""):
        with self.connect() as db:
            db.execute("UPDATE operations SET state=?, result=? WHERE id=?", (state, result, operation_id))

    def retrieve(self, snapshot_id: str, question: str, limit: int = 8) -> list[dict]:
        import re

        terms = re.findall(r"[A-Za-z0-9]{3,}", question)[:20]
        if not terms:
            return []
        query = " OR ".join('"' + term + '"' for term in terms)
        with self.connect() as db:
            rows = db.execute(
                """SELECT document_id, page, content FROM passages
                WHERE passages MATCH ? AND snapshot_id=? ORDER BY rank LIMIT ?""",
                (query, snapshot_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]


def changes(previous: Snapshot, current: Snapshot) -> list[str]:
    old = {json.dumps(c.model_dump(exclude={"id", "evidence"}), sort_keys=True) for c in previous.claims}
    new = {json.dumps(c.model_dump(exclude={"id", "evidence"}), sort_keys=True) for c in current.claims}
    result = [f"{len(new - old)} new or changed findings; {len(old - new)} previous findings not reproduced."]
    old_hashes = {d.url or d.title: d.sha256 for d in previous.documents}
    changed = [
        d.title
        for d in current.documents
        if (d.url or d.title) in old_hashes and d.sha256 != old_hashes[d.url or d.title]
    ]
    if changed:
        result.append("Changed documents: " + ", ".join(changed))
    return result
