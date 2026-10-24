"""Explicitly approved, single-attempt external evidence collection."""
import base64
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import subprocess
import sys
from urllib.parse import urlsplit
from .engine import event
from .store import now


def validate_spec(spec):
    if not isinstance(spec, dict) or set(spec) != {'kind', 'url', 'max_bytes'}:
        raise ValueError('Invalid external action specification')
    if spec['kind'] != 'https-get-v1':
        raise ValueError('Unsupported external action kind')
    if type(spec['max_bytes']) is not int or not 1 <= spec['max_bytes'] <= 1048576:
        raise ValueError('max_bytes must be 1..1048576')
    url = spec['url']
    if not isinstance(url, str) or len(url) > 2048 or not url.isascii() or any(ord(c) <= 32 or ord(c) == 127 for c in url):
        raise ValueError('URL must be an ASCII URL of at most 2048 characters without whitespace')
    parts = urlsplit(url)
    if (parts.scheme != 'https' or not parts.hostname or parts.username is not None
            or parts.password is not None or parts.port not in (None, 443) or parts.fragment):
        raise ValueError('Only HTTPS port 443 without credentials or fragments is supported')
    return parts


def fingerprint(row):
    scope = {k: row[k] for k in ('hypothesis_id', 'description', 'max_cost_cents', 'spec', 'expires_at')}
    return sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()


def request_get(store, hypothesis_id, url, max_bytes=65536, expires_hours=24):
    spec = {'kind': 'https-get-v1', 'url': url, 'max_bytes': max_bytes}
    validate_spec(spec)
    if type(expires_hours) is not int or not 1 <= expires_hours <= 24:
        raise ValueError('expires_hours must be 1..24')
    expires = (datetime.now(timezone.utc) + timedelta(hours=expires_hours)).isoformat()
    with store.db:
        aid = store.db.execute('''INSERT INTO actions(hypothesis_id,description,max_cost_cents,created_at)
          VALUES(?,?,0,?)''', (hypothesis_id, 'Fetch public evidence: ' + url, now())).lastrowid
        store.db.execute('INSERT INTO action_requests(id,spec,expires_at) VALUES(?,?,?)',
                         (aid, json.dumps(spec, sort_keys=True), expires))
    event('action_requested', action_id=aid)
    return aid


def seal_approval(db, action_id):
    row = db.execute('SELECT a.*, r.spec, r.expires_at FROM actions a JOIN action_requests r ON a.id=r.id WHERE a.id=?', (action_id,)).fetchone()
    if row:
        validate_spec(json.loads(row['spec']))
        if row['expires_at'] <= now():
            raise ValueError('Request has expired; create a new request')
        db.execute('UPDATE action_requests SET approval_hash=? WHERE id=?', (fingerprint(row), action_id))


def fetch(spec):
    # Child timeout bounds DNS, TLS, headers and body together. No shell or retries.
    worker = subprocess.run([sys.executable, '-m', 'ear.http_worker'],
                            input=json.dumps(spec), text=True, capture_output=True, timeout=15)
    if worker.returncode:
        raise ValueError('HTTPS fetch failed: ' + worker.stderr.strip()[:1000])
    return json.loads(worker.stdout)


def execute_action(store, action_id):
    # Acquire the write lock before checking the approval; competing processes cannot claim twice.
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        row = store.db.execute('SELECT a.*, r.spec, r.expires_at, r.approval_hash FROM actions a JOIN action_requests r ON a.id=r.id WHERE a.id=?', (action_id,)).fetchone()
        if row is None or row['status'] != 'approved':
            raise ValueError('Action must have an executable specification and unused approval')
        if row['expires_at'] <= now() or fingerprint(row) != row['approval_hash']:
            raise ValueError('Approval expired or request changed; create a new request')
        if row['max_cost_cents'] != 0:
            raise ValueError('This executor does not support paid actions')
        spec = json.loads(row['spec'])
        validate_spec(spec)
        store.db.execute("UPDATE actions SET status='executing' WHERE id=?", (action_id,))
        store.db.execute('UPDATE action_requests SET started_at=? WHERE id=?', (now(), action_id))
    event('action_started', action_id=action_id)
    try:
        result = fetch(spec)
        body = base64.b64decode(result['body_base64'], validate=True)
        if len(body) > spec['max_bytes'] or sha256(body).hexdigest() != result['sha256']:
            raise ValueError('Invalid fetch result')
        result['url'] = spec['url']
        result['retrieved_at'] = now()
        result['classification'] = 'external_source_unverified'
        with store.db:
            eid = store.db.execute('INSERT INTO evidence(hypothesis_id,kind,source,content,created_at) VALUES(?,?,?,?,?)',
                                   (row['hypothesis_id'], 'source', spec['url'], json.dumps(result, sort_keys=True), now())).lastrowid
            store.db.execute("UPDATE actions SET status='completed' WHERE id=?", (action_id,))
            store.db.execute('UPDATE action_requests SET result=?,evidence_id=?,finished_at=? WHERE id=?',
                             (json.dumps(result, sort_keys=True), eid, now(), action_id))
    except Exception as exc:
        with store.db:
            store.db.execute("UPDATE actions SET status='failed' WHERE id=?", (action_id,))
            store.db.execute('UPDATE action_requests SET error=?,finished_at=? WHERE id=?', (str(exc), now(), action_id))
        event('action_failed', action_id=action_id, error=str(exc))
        raise ValueError('Action failed; approval consumed: ' + str(exc)) from exc
    event('action_completed', action_id=action_id, evidence_id=eid)
    return {'action_id': action_id, 'status': 'completed', 'evidence_id': eid,
            'bytes': len(body), 'sha256': result['sha256']}
