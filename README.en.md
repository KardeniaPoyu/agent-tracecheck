# Agent TraceCheck

Lint agent trajectories before they become SFT or RL training data.

[中文文档](README.md) · [Input contract](docs/format.md) · [Rules](docs/rules.md) · [Changelog](CHANGELOG.md)

Python 3.11+ · no third-party runtime dependencies · offline · MIT

## Install from source

```bash
git clone https://github.com/KardeniaPoyu/agent-tracecheck.git
cd agent-tracecheck
python -m venv .venv
# Activate .venv for your shell, then:
python -m pip install -e .
agent-tracecheck scan examples/clean.jsonl
agent-tracecheck scan examples/broken.jsonl --json reports/report.json --html reports/report.html
```

The broken fixture intentionally returns exit code 1. Open the HTML file locally to search and filter findings. No network resources are loaded by the report.

## What it checks

36 rules cover tool-call pairing and order, retry duplicates, inconsistent supervision, split leakage, reward validity and declared-outcome consistency, truncation, EOS and token-level masks. Diagnostics include source locations, JSON pointers, related records, source hashes and remediation advice.

```bash
agent-tracecheck scan data/ --exclude 'reports/*' --config tracecheck.toml --fail-on warning
agent-tracecheck scan train.jsonl.gz test.jsonl.gz --sarif reports/results.sarif
agent-tracecheck repro reports/report.json ISSUE_ID --output reports/repro.jsonl
agent-tracecheck scan reports/repro.jsonl --config reports/repro.jsonl.meta.json
```

Inputs: JSONL/NDJSON, JSON objects/arrays, a trajectories wrapper, and gzip equivalents. Supported message aliases are OpenAI-style messages and ShareGPT conversations. Raw framework traces and Responses streaming events require explicit conversion.

Reproductions preserve the target rule and are replay-verified. Completed minimization is 1-minimal under top-level field and whole-message deletion, not globally minimal; nested/token data is retained. Source records must still match their hashes. Empty/invalid JSON inputs use direct source diagnostics instead of JSONL reproduction.

Reward rules validate consistency, not real-world correctness. Deduplication normalizes tool-call IDs but preserves content, arguments, order and outputs. Token-role leakage requires explicit token_roles. JSONL reading is incremental; findings accumulate in memory and each record must fit in memory. Duplicate metadata uses temporary SQLite storage.

Exit codes: 0 = no threshold violation, 1 = quality gate failed, 2 = operational/configuration error, 130 = interrupted. Use --fail-on none for report-only mode. Inspect all dataset splits in one invocation for leakage detection.

## Development

```bash
python -m pip install -e '.[dev]'
ruff check src tests
python -m pytest -q
python -m build
```

See CONTRIBUTING.md and SECURITY.md. The project is alpha; calibrate reward policy and heuristic precision on your own dataset before using it as a production gate. No automatic reward correction or record deletion is performed.
