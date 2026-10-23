"""Allowlisted, bounded synthetic allocation experiment. No dynamic code execution."""
from hashlib import sha256
import json

VERSION = 'allocation-v1'
DEFAULT = {'items': [4, 4, 6, 6], 'capacity': 10, 'unit_cost_cents': 100,
           'coordination_cost_cents': 25}


def validate(config):
    if not isinstance(config, dict) or set(config) != set(DEFAULT):
        raise ValueError('Expected exactly: ' + ', '.join(DEFAULT))
    items = config['items']
    cap = config['capacity']
    if type(cap) is not int or not 1 <= cap <= 10000:
        raise ValueError('capacity must be an integer in 1..10000')
    if not isinstance(items, list) or not 1 <= len(items) <= 1000:
        raise ValueError('items must contain 1..1000 integers')
    if any(type(x) is not int or not 1 <= x <= cap for x in items):
        raise ValueError('Each item must be an integer in 1..capacity')
    for key in ('unit_cost_cents', 'coordination_cost_cents'):
        if type(config[key]) is not int or not 0 <= config[key] <= 1000000:
            raise ValueError(key + ' must be an integer in 0..1000000')


def pack(items, capacity):
    remaining = []
    for item in items:
        for i, space in enumerate(remaining):
            if space >= item:
                remaining[i] -= item
                break
        else:
            remaining.append(capacity - item)
    return len(remaining)


def run(config):
    validate(config)
    baseline = pack(config['items'], config['capacity'])
    candidate = pack(sorted(config['items'], reverse=True), config['capacity'])
    gross = (baseline - candidate) * config['unit_cost_cents']
    net = gross - config['coordination_cost_cents']
    canonical = json.dumps(config, sort_keys=True, separators=(',', ':'))
    return {'experiment_version': VERSION, 'config_sha256': sha256(canonical.encode()).hexdigest(),
            'classification': 'synthetic', 'baseline_units': baseline,
            'candidate_units': candidate, 'gross_savings_cents': gross,
            'net_model_advantage_cents': net, 'cash_received_cents': 0,
            'cash_spent_cents': 0, 'real_world_profitability': 'not_demonstrated',
            'finding': 'supported_in_model' if net > 0 else 'not_supported_in_model',
            'limitations': 'Known packing heuristic; constructed data; no demand, buyer, collection, or novelty evidence.'}
