# Contributing

Use Python 3.11 or newer. Install with `python -m pip install -e ".[dev]"`.

Run `python -m pytest`, `ruff check src tests`, and `python -m build` before submitting changes.

Every new rule needs a stable identifier in rules.py, a precise input contract, a positive test and a realistic negative test. Prefer deterministic evidence over guesses about natural-language correctness. Severity is policy, so make uncertain findings warnings. Do not add network calls to scanning or execute user-provided tool arguments.

Keep source messages intact during normalization. New adapters must preserve source pointers. For bug reports, include a sanitized reproduction, the config/metadata sidecar, Python version, expected behavior and actual rule IDs. Never include real credentials or private trajectories.

No generated build artifacts, user data, virtual environments or reports should be committed. The examples are synthetic fixtures.
