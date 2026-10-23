import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ear import experiment
from ear.engine import demo, execute
from ear.store import Store

class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'research.sqlite3')
        self.store = Store(self.path)
    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()
    def test_full_cycle_survives_reopen(self):
        result = demo(self.store)
        self.assertEqual((result['baseline_units'], result['candidate_units']), (3, 2))
        self.assertEqual(result['net_model_advantage_cents'], 75)
        self.assertEqual(result['cash_received_cents'], 0)
        self.assertEqual(result['real_world_profitability'], 'not_demonstrated')
        self.store.close()
        self.store = Store(self.path)
        report = self.store.report()
        self.assertEqual(len(report['evidence']), 1)
        self.assertEqual(report['runs'][0]['status'], 'completed')
        self.assertEqual(report['findings'][0]['run_id'], result['run_id'])
        self.assertEqual(json.loads(report['runs'][0]['result']), {k:v for k,v in result.items() if k != 'run_id'})
    def test_reproducible_and_input_hash_sensitive(self):
        a = experiment.run(experiment.DEFAULT)
        self.assertEqual(a, experiment.run(dict(experiment.DEFAULT)))
        b = experiment.run({**experiment.DEFAULT, 'coordination_cost_cents': 200})
        self.assertNotEqual(a['config_sha256'], b['config_sha256'])
        self.assertEqual(b['net_model_advantage_cents'], -100)
        self.assertEqual(b['finding'], 'not_supported_in_model')
    def test_non_object_config(self):
        for config in (None, [], 42, 'text'):
            with self.subTest(config=config), self.assertRaises(ValueError):
                experiment.run(config)

    def test_no_gain_control(self):
        result = experiment.run({**experiment.DEFAULT, 'items': [6,4,6,4]})
        self.assertEqual(result['baseline_units'], 2)
        self.assertEqual(result['net_model_advantage_cents'], -25)
    def test_bounds_and_types(self):
        for changes in ({'items': []}, {'items': [11]}, {'items': [True]},
                        {'items': [1]*1001}, {'capacity': 0}, {'capacity': 10001},
                        {'unit_cost_cents': -1}, {'coordination_cost_cents': 1.5},
                        {'coordination_cost_cents': float('nan')}, {'extra': 1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                experiment.run({**experiment.DEFAULT, **changes})
    def test_failure_is_persisted_without_finding(self):
        hid = self.store.hypothesis('Failure test')
        with patch('ear.engine.experiment.run', side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):
                execute(self.store, hid, experiment.DEFAULT)
        report = self.store.report()
        self.assertEqual(report['runs'][0]['status'], 'failed')
        self.assertEqual(report['runs'][0]['error'], 'injected')
        self.assertEqual(report['findings'], [])
    def test_foreign_keys_and_invalid_evidence(self):
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.evidence(99, 'source', 'url', 'claim')
        hid = self.store.hypothesis('Test')
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.evidence(hid, 'fabricated', 'url', 'claim')
    def test_external_gate_and_no_executor(self):
        hid = self.store.hypothesis('Test external gate')
        aid = self.store.request_action(hid, 'Potential paid pilot', 500)
        self.assertEqual(self.store.report()['actions'][0]['status'], 'pending')
        with self.assertRaises(ValueError):
            self.store.decide(aid, True, '', 'missing reviewer')
        self.store.decide(aid, False, 'human', 'Insufficient evidence')
        with self.assertRaises(ValueError):
            self.store.decide(aid, True, 'human', 'Cannot overwrite review')
        with self.assertRaises(ValueError):
            execute(self.store, hid, experiment.DEFAULT, 'external-shell')
        aid = self.store.request_action(hid, 'Zero-cost external action')
        self.store.decide(aid, True, 'human', 'Reviewed exact scope')
        self.assertEqual(self.store.report()['actions'][1]['status'], 'approved')
        self.assertEqual(self.store.report()['runs'], [])
    def test_cli_and_json_logs_across_processes(self):
        log = str(Path(self.tmp.name) / 'events.jsonl')
        def cli(*args):
            return subprocess.run([sys.executable, '-m', 'ear', '--db', self.path,
                                   '--log', log, *args], text=True, capture_output=True)
        first = cli('demo')
        self.assertEqual(first.returncode, 0, first.stderr)
        report = cli('report')
        self.assertEqual(len(json.loads(report.stdout)['findings']), 1)
        events = [json.loads(line) for line in Path(log).read_text().splitlines()]
        self.assertEqual([e['event'] for e in events], ['run_started', 'run_completed'])
        bad = cli('hypothesis', '')
        self.assertEqual(bad.returncode, 1)
        self.assertIn('error', json.loads(bad.stderr))

if __name__ == '__main__':
    unittest.main()
