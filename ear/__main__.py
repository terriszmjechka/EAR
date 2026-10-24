import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path
from .store import Store
from .engine import demo, execute
from .actions import request_get, execute_action


def main(argv=None):
    p = argparse.ArgumentParser(description='Persistent economic mechanism research; bounded experiments and approved evidence collection')
    p.add_argument('--db', default='ear.sqlite3')
    p.add_argument('--log', default='ear.jsonl')
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('init', 'demo', 'report'):
        sub.add_parser(name)
    h = sub.add_parser('hypothesis'); h.add_argument('statement')
    e = sub.add_parser('evidence'); e.add_argument('hypothesis_id', type=int)
    e.add_argument('--kind', choices=['synthetic','observation','source'], required=True)
    e.add_argument('--source', required=True); e.add_argument('--content', required=True)
    r = sub.add_parser('run'); r.add_argument('hypothesis_id', type=int)
    r.add_argument('--config', type=Path, required=True)
    a = sub.add_parser('request-action'); a.add_argument('hypothesis_id', type=int)
    a.add_argument('description'); a.add_argument('--max-cost-cents', type=int, default=0)
    d = sub.add_parser('decide-action'); d.add_argument('action_id', type=int)
    d.add_argument('--decision', choices=['approve','reject'], required=True)
    d.add_argument('--reviewer', required=True); d.add_argument('--note', required=True)
    g = sub.add_parser('request-get'); g.add_argument('hypothesis_id', type=int)
    g.add_argument('url'); g.add_argument('--max-bytes', type=int, default=65536)
    g.add_argument('--expires-hours', type=int, default=24)
    x = sub.add_parser('execute-action'); x.add_argument('action_id', type=int)
    args = p.parse_args(argv)
    logging.basicConfig(filename=args.log, level=logging.INFO, format='%(message)s', force=True)
    store = None
    try:
        store = Store(args.db)
        match args.command:
            case 'init': out = {'schema_version': 2}
            case 'demo': out = demo(store)
            case 'report': out = store.report()
            case 'hypothesis': out = {'hypothesis_id': store.hypothesis(args.statement)}
            case 'evidence': out = {'evidence_id': store.evidence(args.hypothesis_id, args.kind, args.source, args.content)}
            case 'run':
                if args.config.stat().st_size > 65536:
                    raise ValueError('Config exceeds 64 KiB limit')
                out = execute(store, args.hypothesis_id, json.loads(args.config.read_text()))
            case 'request-action': out = {'action_id': store.request_action(args.hypothesis_id, args.description, args.max_cost_cents), 'status': 'pending'}
            case 'request-get':
                out = {'action_id': request_get(store, args.hypothesis_id, args.url, args.max_bytes, args.expires_hours), 'status': 'pending'}
            case 'execute-action': out = execute_action(store, args.action_id)
            case 'decide-action':
                store.decide(args.action_id, args.decision == 'approve', args.reviewer, args.note)
                out = {'status': 'recorded', 'executed': False}
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 1
    finally:
        if store:
            store.close()


if __name__ == '__main__':
    sys.exit(main())
