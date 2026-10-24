# EAR — Economic research testbed

A minimal executable foundation for the AES research direction: formulate a mechanism, preserve evidence, run a bounded experiment, evaluate it, and retain findings across sessions. Explore resource organization, allocation, information and transformation without requiring a conventional business model. This is not an autonomous income generator.

Python 3.12+; runtime and tests use only the standard library. The demo and tests need no API keys, network access, purchases, or third-party runtime packages. Approved HTTPS evidence collection requires network access.

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

EAR can execute explicitly approved public HTTPS GET requests and retain their responses as source evidence. It does not execute arbitrary commands, authenticated APIs, POST requests, purchases, trading, messages, or paid actions. Review a URL carefully: a poorly designed server can give even GET requests side effects. Do not put secrets or action-triggering URLs into research requests.

From a fresh database, create a hypothesis, request an exact fetch, inspect it, approve it as the human operator, then execute:

```sh
python -m ear hypothesis 'Can this public source support a research hypothesis?'
python -m ear request-get 1 https://example.com/ --max-bytes 65536 --expires-hours 24
python -m ear report
# Use actual returned IDs; approve only after reviewing the stored request.
python -m ear decide-action 1 --decision approve --reviewer 'Your name' --note 'Reviewed exact URL, limits, and purpose'
python -m ear execute-action 1
python -m ear report
```

Each approval is bound to the exact request, description, hypothesis, zero proposed cost, byte limit, and expiry. Requests expire 1–24 hours after creation, not after approval. A competing process cannot claim the same approval twice. States are pending → approved/rejected → executing → completed/failed. An attempt consumes approval even if it fails; there are no automatic retries. A crash may leave `executing`; investigate before creating another request because the server may already have received it.

Transport accepts HTTPS port 443, blocks nonpublic/multicast/reserved destination addresses, pins the checked address for the connection and verifies TLS against the original hostname. Redirects, compression, credentials and custom headers are unsupported. Responses are capped at the approved limit (maximum 1 MiB, plus one sentinel byte read to detect overflow). A worker has a 15-second total deadline including DNS, with 5-second socket timeouts. Network and platform restrictions still apply. The response's raw bytes are stored as base64 with SHA-256, HTTP status, content type, URL and retrieval time, atomically with the linked evidence and completed action. This proves retrieval, not the source's truth or profitability. Returned content is untrusted data and is never executed.

Generic `request-action` proposals remain available for planning and review, including nonzero proposed cost, but cannot execute through this adapter. Existing version-1 approvals remain historical records and cannot authorize new executable actions. Version-1 databases upgrade automatically by adding `action_requests`; existing records are preserved. Back up research databases before upgrading. Newer unsupported schema versions are rejected.

The local operator supplies the reviewer identity; approval is an audit control, not authentication or protection against someone who can edit the database or run arbitrary Python. Research automation must never approve its own requests. There is no financial ledger or spending integration. Zero proposed cost means the adapter invokes no paid API, not that bandwidth, platform or operational costs cannot exist.

## Persistence and failure behavior

SQLite foreign keys link hypotheses → evidence/runs → findings. Run states are `running`, `completed`, `failed`. Completed results and findings commit in one transaction. Exceptions mark a run failed and retain the error without inventing a finding. Abrupt process termination may leave `running`; inspect before rerunning (reruns append independent records). Logs contain start/completion/failure events with run IDs and UTC timestamps. SQLite is the authority; a crash may interrupt a log write. Schema version 2 supports additive upgrades from version 1. Keep private evidence out of shared reports and commits.

## Structure and extending the research

- `ear/store.py`: persistent research, approvals, and schema upgrade.
- `ear/actions.py`: request, approval binding, execution and evidence lifecycle.
- `ear/http_worker.py`: bounded HTTPS transport in a timed worker.
- `ear/experiment.py`: deterministic mechanism, validation and model economics.
- `ear/engine.py`: experiment lifecycle and findings.
- `ear/__main__.py`: CLI and JSON logging.
- `tests/test_ear.py` and `tests/test_actions.py`: reproducibility, persistence, adverse economics, bounds, failures, approvals, transport, schema upgrade and CLI.

To add a mechanism, predeclare the resource transformation, baseline, falsification criterion, bounded inputs, direct/coordination costs, provenance, and evidence needed to establish value capture. Implement a reviewed local function, version it, add it to the explicit engine allowlist and CLI, and test adverse cases. Preserve rejected hypotheses and failed acquisitions. Compare technical feasibility, measurable advantage, and retained/collected value separately. This demo validates the research plumbing; it does not establish allocation research as a commercial focus.
