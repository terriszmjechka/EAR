"""SQLite research memory. Monetary model values never enter a cash ledger."""
import json
import sqlite3
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        if self.db.execute('PRAGMA user_version').fetchone()[0] > 2:
            self.db.close()
            raise ValueError('Database schema is newer than this application')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS hypotheses (
          id INTEGER PRIMARY KEY, statement TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS evidence (
          id INTEGER PRIMARY KEY, hypothesis_id INTEGER NOT NULL REFERENCES hypotheses(id),
          kind TEXT NOT NULL CHECK(kind IN ('synthetic','observation','source')),
          source TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runs (
          id INTEGER PRIMARY KEY, hypothesis_id INTEGER NOT NULL REFERENCES hypotheses(id),
          experiment TEXT NOT NULL, config TEXT NOT NULL, status TEXT NOT NULL,
          result TEXT, error TEXT, created_at TEXT NOT NULL, finished_at TEXT);
        CREATE TABLE IF NOT EXISTS findings (
          id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL UNIQUE REFERENCES runs(id),
          conclusion TEXT NOT NULL, next_step TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS actions (
          id INTEGER PRIMARY KEY, hypothesis_id INTEGER NOT NULL REFERENCES hypotheses(id),
          description TEXT NOT NULL, max_cost_cents INTEGER NOT NULL CHECK(max_cost_cents>=0),
          status TEXT NOT NULL DEFAULT 'pending', reviewer TEXT, decision_note TEXT,
          created_at TEXT NOT NULL, decided_at TEXT);
        CREATE TABLE IF NOT EXISTS action_requests (
          id INTEGER PRIMARY KEY REFERENCES actions(id), spec TEXT NOT NULL,
          expires_at TEXT NOT NULL, approval_hash TEXT, started_at TEXT, finished_at TEXT,
          result TEXT, error TEXT, evidence_id INTEGER REFERENCES evidence(id));
        PRAGMA user_version=2;
        ''')

    def close(self):
        self.db.close()

    def insert(self, table, **fields):
        # Only internal callers supply identifiers; values always use parameters.
        with self.db:
            cursor = self.db.execute(f"INSERT INTO {table} ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})", tuple(fields.values()))
        return cursor.lastrowid

    def hypothesis(self, statement):
        if not statement.strip():
            raise ValueError('Hypothesis must not be empty')
        return self.insert('hypotheses', statement=statement, created_at=now())

    def evidence(self, hypothesis_id, kind, source, content):
        if not source.strip() or not content.strip():
            raise ValueError('Evidence needs a source and content')
        return self.insert('evidence', hypothesis_id=hypothesis_id, kind=kind,
                           source=source, content=content, created_at=now())

    def request_action(self, hypothesis_id, description, max_cost_cents=0):
        if not description.strip() or type(max_cost_cents) is not int or max_cost_cents < 0:
            raise ValueError('Action needs a description and nonnegative integer cost')
        return self.insert('actions', hypothesis_id=hypothesis_id, description=description,
                           max_cost_cents=max_cost_cents, created_at=now())

    def decide(self, action_id, approve, reviewer, note):
        if not reviewer.strip() or not note.strip():
            raise ValueError('A named human reviewer and decision note are required')
        with self.db:
            changed = self.db.execute('''UPDATE actions SET status=?, reviewer=?, decision_note=?,
              decided_at=? WHERE id=? AND status='pending' ''',
              ('approved' if approve else 'rejected', reviewer, note, now(), action_id)).rowcount
            if changed != 1:
                raise ValueError('Action missing or already decided')
            if approve:
                from .actions import seal_approval
                seal_approval(self.db, action_id)

    def report(self):
        return {table: [dict(row) for row in self.db.execute(f'SELECT * FROM {table} ORDER BY id')]
                for table in ('hypotheses', 'evidence', 'runs', 'findings', 'actions', 'action_requests')}
