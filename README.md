# EAR — Economic research testbed

A minimal executable foundation for the AES research direction: formulate a mechanism, preserve evidence, run a bounded experiment, evaluate it, and retain findings across sessions. Explore resource organization, allocation, information and transformation without requiring a conventional business model. This is not an autonomous income generator.

Python 3.12+; runtime and tests use only the standard library. No API keys, network access, purchases, or third-party runtime packages are needed.

## Run a complete cycle

From the repository root:

```sh
python -m ear demo
python -m ear report
python -m unittest discover -s tests -v
```

`demo` registers a new hypothesis and synthetic evidence, executes the experiment, evaluates its economics, and saves a finding. Each invocation intentionally creates a separate run/hypothesis; nothing is overwritten. `report` returns all persistent records as JSON. SQLite defaults to `ear.sqlite3`; structured JSON-line logs default to `ear.jsonl`. These local research records are excluded from git. Back them up yourself; close active processes before copying the database.

Optional installed CLI: `python -m pip install -e .`, then `ear demo`. Installation may download the build backend; module commands above work offline without installation.

## Synthetic experiment and interpretation

The fixed `allocation-v1` experiment compares first-fit packing in input order with first-fit packing after descending sorting. This is an established heuristic, not an invention or optimality claim. Indivisible demands are packed into identical resource units of capacity 10.

| Measurement | Default result |
| --- | ---: |
| Synthetic demands | 4, 4, 6, 6 |
| Baseline resource units | 3 |
| Reordered resource units | 2 |
| Assumed unit cost | 100 cents |
| Assumed coordination cost | 25 cents |
| Modeled gross savings | 100 cents |
| Modeled net advantage | 75 cents |
| Actual receipts and spending | 0 cents |

Results record `classification=synthetic` and `real_world_profitability=not_demonstrated`. Sorting saves nothing on the control `[6,4,6,4]`, where coordination makes the net negative. A coordination cost of 200 cents also reverses the default result. Tests cover both. This constructed workload does not establish typical performance, willingness to pay, revenue, novelty, or collectibility. Model savings never become cash ledger entries.

## Your own research session

```sh
python -m ear --db research.sqlite3 hypothesis 'Can demand reordering reduce resource use after coordination costs?'
# Use the returned hypothesis_id (1 in a fresh database).
python -m ear --db research.sqlite3 evidence 1 --kind source --source 'local:protocol-v1' --content 'Predeclared comparison; preserve negative results.'
python -m ear --db research.sqlite3 run 1 --config example-config.json
python -m ear --db research.sqlite3 report > report.json
```

Evidence kinds are `synthetic`, `observation`, or `source`: user-declared provenance labels, not verification by EAR. Store references and exact observations; do not present assumptions as observations. Configurations are stored alongside experiment version and a canonical SHA-256 hash. Repeat the same config/version to reproduce metrics; run IDs and timestamps intentionally differ. Source code in git anchors the implementation. `report` preserves raw config/result JSON strings within each run.

Inputs must contain exactly the four keys in `example-config.json`: 1–1000 integer demands, capacity 1–10000, demands within capacity, integer modeled costs 0–1000000 cents. CLI config files are limited to 64 KiB. At most two packing passes of up to 1000 demands run, with at most 1000 bin checks per demand. No arbitrary Python/shell execution, dynamic plugins or network client exists. This is bounded allowlisted computation, **not an OS security sandbox for untrusted code**.

## External actions and risk

All external actions, including zero-cost publication or outreach, must be proposed separately:

```sh
python -m ear request-action 1 'Describe the exact proposed external action' --max-cost-cents 0
python -m ear decide-action 1 --decision reject --reviewer 'Your name' --note 'Reason and reviewed scope'
```

Requests begin pending. A human can record approval or rejection once with identity and rationale. The CLI trusts the local operator's identity; this is an audit gate, not authentication or tamper resistance. **No external-action executor exists**, even for approved requests. Approval records do not spend money or send anything. Research automation must never approve its own requests. Future integrations must enforce explicit scope, expiry, one-time consumption and financial exposure limits before execution. A proposed maximum cost is not a balance, reservation, or spend authorization. This version has zero real financial exposure from experiments and no purchasing, trading, billing, scheduler, paid model calls or financial ledger.

## Persistence and failure behavior

SQLite foreign keys link hypotheses → evidence/runs → findings. Run states are `running`, `completed`, `failed`. Completed results and findings commit in one transaction. Exceptions mark a run failed and retain the error without inventing a finding. Abrupt process termination may leave `running`; inspect before rerunning (reruns append independent records). Logs contain start/completion/failure events with run IDs and UTC timestamps. SQLite is the authority; a crash may interrupt a log write. Schema version 1 is for fresh databases; migrations are not implemented. Keep private evidence out of shared reports and commits.

## Structure and extending the research

- `ear/store.py`: persistent research and approval records.
- `ear/experiment.py`: deterministic mechanism, validation and model economics.
- `ear/engine.py`: experiment lifecycle and findings.
- `ear/__main__.py`: CLI and JSON logging.
- `tests/test_ear.py`: reproducibility, persistence, adverse economics, bounds, failures, gates and CLI.

To add a mechanism, predeclare the resource transformation, baseline, falsification criterion, bounded inputs, direct/coordination costs, provenance, and evidence needed to establish value capture. Implement a reviewed local function, version it, add it to the explicit engine allowlist and CLI, and test adverse cases. Preserve rejected hypotheses and failed acquisitions. Compare technical feasibility, measurable advantage, and retained/collected value separately. This demo validates the research plumbing; it does not establish allocation research as a commercial focus.
