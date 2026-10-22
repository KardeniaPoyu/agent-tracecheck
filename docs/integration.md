# Integrating with SFT / RL pipelines

1. Export accepted and failed attempts with immutable sample IDs and task/attempt provenance.
2. Preserve ordered tool calls/results. Never invent missing results during export.
3. Before tokenization, scan for pairing, duplicate supervision and reward problems.
4. Assign splits after deduplication. Scan all splits together with explicit split fields.
5. After chat templating, truncation and packing, export aligned IDs, masks and token_roles; scan again.
6. Quarantine error records for review. Export reproductions for debugging; rerun the original dataset after fixing the producer.

```python
from agent_tracecheck import Config, Record, Source, scan_records

def exported_records(training_rows):
    for index, row in enumerate(training_rows):
        # Adapt your trainer's field names explicitly here.
        yield Record(row, Source("trainer-export", index + 1, index))

def quality_gate(training_rows):
    report = scan_records(exported_records(training_rows), Config(reward_min=-1, reward_max=1))
    if any(issue.severity == "error" for issue in report.issues):
        raise ValueError(f"Training data failed: {len(report.issues)} findings")
    return report
```

For filesystem reproductions, export to a persistent JSONL file and use scan(path). In-memory Source references cannot be reopened by the repro CLI.

## CI exit-code gate

```yaml
- run: python -m pip install .
- run: agent-tracecheck scan data/ --config tracecheck.toml --json reports/report.json --sarif reports/report.sarif
- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: trajectory-quality
    path: reports/
```

Restrict access to artifacts containing dataset paths or identifiers. An error threshold is appropriate for structural rules; promote heuristics only after measuring precision on your data. The tool does not perform automatic deletion, reward rewriting or train/test redistribution.
