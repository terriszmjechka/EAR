"""One complete local research cycle with auditable success/failure states."""
import json
import logging
from . import experiment
from .store import now

LOG = logging.getLogger('ear')


def event(name, **fields):
    LOG.info(json.dumps({'time': now(), 'event': name, **fields}, sort_keys=True))


def execute(store, hypothesis_id, config, experiment_name='allocation-v1'):
    # Reject arbitrary commands/plugins, including any proposed external action.
    if experiment_name != experiment.VERSION:
        raise ValueError('Only the local allocation-v1 experiment is executable')
    experiment.validate(config)
    config = json.loads(json.dumps(config))
    run_id = store.insert('runs', hypothesis_id=hypothesis_id, experiment=experiment_name,
                          config=json.dumps(config, sort_keys=True), status='running', created_at=now())
    event('run_started', run_id=run_id, hypothesis_id=hypothesis_id)
    try:
        result = experiment.run(config)
        with store.db:
            store.db.execute('UPDATE runs SET status=?, result=?, finished_at=? WHERE id=?',
                             ('completed', json.dumps(result, sort_keys=True), now(), run_id))
            store.db.execute('INSERT INTO findings(run_id,conclusion,next_step,created_at) VALUES(?,?,?,?)',
                             (run_id, result['finding'],
                              'Test non-constructed workloads and measured coordination costs; establish a value-capture path before claiming profit.', now()))
    except Exception as exc:
        with store.db:
            store.db.execute('UPDATE runs SET status=?,error=?,finished_at=? WHERE id=?',
                             ('failed', str(exc), now(), run_id))
        event('run_failed', run_id=run_id, error=str(exc))
        raise
    event('run_completed', run_id=run_id, finding=result['finding'])
    return {'run_id': run_id, **result}


def demo(store):
    hid = store.hypothesis('Can reordering indivisible resource demands reduce modeled resource consumption after coordination costs?')
    store.evidence(hid, 'synthetic', 'ear.experiment.DEFAULT',
                   'Constructed workload [4,4,6,6], capacity 10; unit cost 100 cents, coordination 25 cents. Not market observations.')
    return execute(store, hid, experiment.DEFAULT)
