from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from airp.core.models import TRANSITIONS, Run, State, canonical, digest, now


class Conflict(RuntimeError):
    pass


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.connection = sqlite3.connect(path, isolation_level=None, timeout=10)
        path.chmod(0o600)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, version INTEGER NOT NULL, document TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY, run_id TEXT NOT NULL, payload TEXT NOT NULL,
                previous_hash TEXT NOT NULL, hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS target_locks (
                target TEXT PRIMARY KEY, run_id TEXT NOT NULL UNIQUE
            );
        """)

    def close(self) -> None:
        self.connection.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def _event(self, run: Run, actor: str, kind: str) -> None:
        row = self.connection.execute(
            "SELECT hash FROM events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous = row["hash"] if row else "0" * 64
        payload = canonical(
            {
                "run_id": run.id,
                "at": now().isoformat(),
                "actor": actor,
                "kind": kind,
                "state": run.state.value,
                "version": run.version,
                "document_digest": digest(run.model_dump(mode="json")),
            }
        )
        self.connection.execute(
            "INSERT INTO events(run_id,payload,previous_hash,hash) VALUES(?,?,?,?)",
            (run.id, payload, previous, digest({"previous": previous, "payload": payload})),
        )

    def create(self, run: Run) -> None:
        with self.transaction():
            self.connection.execute(
                "INSERT INTO runs VALUES(?,?,?)", (run.id, run.version, run.model_dump_json())
            )
            self._event(run, run.planner, "collected")

    def get(self, run_id: str) -> Run:
        row = self.connection.execute("SELECT document FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError("Unknown run")
        return Run.model_validate_json(row["document"])

    def transition(self, run: Run, state: State, actor: str, **updates: Any) -> Run:
        if state not in TRANSITIONS.get(run.state, frozenset()):
            raise Conflict(f"Illegal transition: {run.state} -> {state}")
        value = run.model_dump()
        value.update(updates, state=state, version=run.version + 1)
        updated = Run.model_validate(value)
        with self.transaction():
            cursor = self.connection.execute(
                "UPDATE runs SET version=?,document=? WHERE id=? AND version=?",
                (updated.version, updated.model_dump_json(), run.id, run.version),
            )
            if cursor.rowcount != 1:
                raise Conflict("Concurrent workflow modification")
            if state == State.EXECUTING:
                assert updated.plan is not None
                try:
                    self.connection.execute(
                        "INSERT INTO target_locks VALUES(?,?)",
                        (f"{run.backend_id}:{updated.plan.target.key}", run.id),
                    )
                except sqlite3.IntegrityError as error:
                    raise Conflict("Target already has an executing workflow") from error
            if run.state == State.EXECUTING and state != State.NEEDS_INTERVENTION:
                self.connection.execute("DELETE FROM target_locks WHERE run_id=?", (run.id,))
            self._event(updated, actor, "transition")
        return updated

    def events(self, run_id: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT * FROM events WHERE run_id=? ORDER BY sequence", (run_id,)
            )
        ]

    def record(self, run_id: str, actor: str, kind: str) -> None:
        with self.transaction():
            self._event(self.get(run_id), actor, kind)

    def verify(self) -> str:
        previous = "0" * 64
        latest: dict[str, str] = {}
        for row in self.connection.execute("SELECT * FROM events ORDER BY sequence"):
            if row["previous_hash"] != previous or row["hash"] != digest(
                {"previous": previous, "payload": row["payload"]}
            ):
                raise Conflict("Audit chain verification failed")
            payload = json.loads(row["payload"])
            if payload["run_id"] != row["run_id"]:
                raise Conflict("Audit run identity mismatch")
            latest[row["run_id"]] = payload["document_digest"]
            previous = row["hash"]
        for row in self.connection.execute("SELECT id,document FROM runs"):
            if latest.get(row["id"]) != digest(json.loads(row["document"])):
                raise Conflict("Workflow document differs from audit checkpoint")
        return previous
