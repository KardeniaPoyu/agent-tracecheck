# Changelog

## 0.2.0

### Fixed

- Empty files, empty arrays and empty API iterators no longer pass quality gates.
- Duplicate JSON keys, nonstandard numeric constants, overflow and excessive JSON nesting are rejected with input diagnostics.
- Reward and mask checks run even when messages are missing or invalid; sample ID collision detection is independent of message validity.
- Invalid mask values no longer cascade into misleading role-leak findings. Empty token arrays are reported.
- Legacy function_call and ambiguous message-array aliases are explicitly rejected instead of silently ignored.
- Invalid JSON config/report shapes fail cleanly; invalid policy types and nonnegative ignore_index are rejected.
- Reproductions validate budget and JSONL extension, enforce source integrity and retain final replay verification.
- Report writes are atomic and cannot overwrite input through a hard link.
- SARIF uses repository-relative, URI-escaped paths where possible.
- Reports snapshot configuration so subsequent caller mutations cannot change the recorded policy.

### Added

- Gzip support for JSON, JSONL and NDJSON.
- Repeatable --exclude glob patterns relative to each input directory.
- Duplicate-index composite indexes, regression tests, English quick start and release documentation.

## 0.1.0

Initial local implementation: trajectory pairing, duplicates, rewards, truncation, masks, reports and replay-verified structural minimization.
