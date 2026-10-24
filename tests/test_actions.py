import base64
from hashlib import sha256
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from ear.actions import execute_action, request_get, validate_spec, fetch
from ear.http_worker import retrieve
from ear.store import Store

BODY = b'example external evidence'
RESULT = {'body_base64': base64.b64encode(BODY).decode(), 'sha256': sha256(BODY).hexdigest(),
          'http_status': 200, 'content_type': 'text/plain'}

class ActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'test.sqlite3')
        self.s = Store(self.path)
        self.hid = self.s.hypothesis('External data test')
    def tearDown(self):
        self.s.close()
        self.tmp.cleanup()
    def request(self):
        return request_get(self.s, self.hid, 'https://example.com/data')
    def approve(self, aid):
        self.s.decide(aid, True, 'Test operator', 'Reviewed exact request')
    def test_approval_required_and_success_persists(self):
        aid = self.request()
        with patch('ear.actions.fetch') as network:
            with self.assertRaises(ValueError):
                execute_action(self.s, aid)
            network.assert_not_called()
        self.approve(aid)
        with patch('ear.actions.fetch', return_value=dict(RESULT)) as network:
            result = execute_action(self.s, aid)
            with self.assertRaises(ValueError):
                execute_action(self.s, aid)
            network.assert_called_once()
        self.s.close(); self.s = Store(self.path)
        self.assertEqual(result['bytes'], len(BODY))
        report = self.s.report()
        self.assertEqual(report['actions'][0]['status'], 'completed')
        saved = json.loads(report['evidence'][0]['content'])
        self.assertEqual(base64.b64decode(saved['body_base64']), BODY)
        self.assertEqual(saved['classification'], 'external_source_unverified')
        self.assertEqual(report['action_requests'][0]['evidence_id'], result['evidence_id'])
    def test_rejected_and_legacy_requests_do_not_execute(self):
        aid = self.request()
        self.s.decide(aid, False, 'Human', 'Rejected')
        legacy = self.s.request_action(self.hid, 'Unspecific external action')
        self.approve(legacy)
        with patch('ear.actions.fetch') as network:
            for action in (aid, legacy):
                with self.assertRaises(ValueError):
                    execute_action(self.s, action)
            network.assert_not_called()
    def test_expired_and_changed_scope_blocked(self):
        aid = self.request(); self.approve(aid)
        with self.s.db:
            self.s.db.execute("UPDATE action_requests SET expires_at='2000-01-01' WHERE id=?", (aid,))
        with patch('ear.actions.fetch') as network:
            with self.assertRaises(ValueError): execute_action(self.s, aid)
            aid2 = self.request(); self.approve(aid2)
            with self.s.db:
                self.s.db.execute("UPDATE actions SET description='changed' WHERE id=?", (aid2,))
            with self.assertRaises(ValueError): execute_action(self.s, aid2)
            network.assert_not_called()
    def test_failed_attempt_consumes_approval(self):
        aid = self.request(); self.approve(aid)
        with patch('ear.actions.fetch', side_effect=TimeoutError('timeout')) as network:
            with self.assertRaises(ValueError): execute_action(self.s, aid)
            with self.assertRaises(ValueError): execute_action(self.s, aid)
            network.assert_called_once()
        report = self.s.report()
        self.assertEqual(report['actions'][0]['status'], 'failed')
        self.assertIn('timeout', report['action_requests'][0]['error'])
        self.assertEqual(report['evidence'], [])
    def test_competing_connection_cannot_execute_twice(self):
        aid = self.request(); self.approve(aid)
        def competing(spec):
            other = Store(self.path)
            try:
                with self.assertRaises(ValueError): execute_action(other, aid)
            finally: other.close()
            return dict(RESULT)
        with patch('ear.actions.fetch', side_effect=competing) as network:
            execute_action(self.s, aid)
            network.assert_called_once()
    def test_v1_upgrade_preserves_records_and_approvals(self):
        aid = self.s.request_action(self.hid, 'Old request')
        self.approve(aid)
        self.s.db.execute('DROP TABLE action_requests')
        self.s.db.execute('PRAGMA user_version=1'); self.s.db.commit()
        self.s.close(); self.s = Store(self.path)
        self.assertEqual(self.s.db.execute('PRAGMA user_version').fetchone()[0], 2)
        self.assertEqual(self.s.report()['actions'][0]['status'], 'approved')
        with self.assertRaises(ValueError): execute_action(self.s, aid)
    def test_url_and_resource_limits(self):
        for url in ('http://example.com', 'https://u:p@example.com', 'https://example.com:8443',
                    'https://example.com/#fragment', 'https://example.com/\r\nheader:x'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                request_get(self.s, self.hid, url)
        for limit in (0, 1048577, True):
            with self.assertRaises(ValueError): request_get(self.s, self.hid, 'https://example.com', limit)
        for hours in (0, 25):
            with self.assertRaises(ValueError): request_get(self.s, self.hid, 'https://example.com', expires_hours=hours)
    def test_private_or_mixed_dns_blocked_before_connect(self):
        for ips in (['127.0.0.1'], ['169.254.169.254'], ['::1'], ['224.0.0.1'], ['93.184.216.34','10.0.0.1']):
            addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip,443)) for ip in ips]
            with patch('ear.http_worker.socket.getaddrinfo', return_value=addresses), patch('ear.http_worker.socket.create_connection') as connect:
                with self.assertRaises(ValueError): retrieve({'kind':'https-get-v1','url':'https://example.com','max_bytes':100})
                connect.assert_not_called()
    def test_transport_pins_ip_validates_tls_and_bounds_body(self):
        response = MagicMock(); response.status = 200
        response.getheader.side_effect = lambda key, default='': default
        response.read.return_value = BODY
        raw = MagicMock(); tls = MagicMock(); conn = MagicMock()
        conn.getresponse.return_value = response
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34',443))]
        with patch('ear.http_worker.socket.getaddrinfo', return_value=addresses), patch('ear.http_worker.socket.create_connection', return_value=raw) as connect, patch('ear.http_worker.ssl.create_default_context') as context, patch('ear.http_worker.http.client.HTTPSConnection', return_value=conn):
            context.return_value.wrap_socket.return_value = tls
            spec = {'kind':'https-get-v1','url':'https://example.com/data?q=1','max_bytes':100}
            result = retrieve(spec)
            self.assertEqual(result['sha256'], RESULT['sha256'])
            connect.assert_called_once_with(('93.184.216.34',443), timeout=5)
            context.return_value.wrap_socket.assert_called_once_with(raw, server_hostname='example.com')
            self.assertEqual(conn.request.call_args.args, ('GET','/data?q=1'))
            response.read.assert_called_with(101)
            response.status = 302
            with self.assertRaises(ValueError): retrieve(spec)
            response.status = 200; response.read.return_value = b'x'*101
            with self.assertRaises(ValueError): retrieve(spec)
    def test_worker_total_timeout_and_no_shell(self):
        spec = {'kind':'https-get-v1','url':'https://example.com','max_bytes':100}
        with patch('ear.actions.subprocess.run', side_effect=subprocess.TimeoutExpired('worker',15)) as run:
            with self.assertRaises(subprocess.TimeoutExpired): fetch(spec)
            self.assertEqual(run.call_args.kwargs['timeout'], 15)
            self.assertNotIn('shell', run.call_args.kwargs)

if __name__ == '__main__': unittest.main()
