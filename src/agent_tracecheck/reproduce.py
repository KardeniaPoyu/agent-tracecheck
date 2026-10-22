"""Replay-verified structural minimization, without executing any agent tools."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict
from pathlib import Path

from .engine import scan_records
from .io import read_records
from .model import Config, Record, Source


def reproduce(report_path: str | Path, issue_id: str, output: str | Path, max_checks: int = 300) -> dict:
    report_path, output = Path(report_path).resolve(), Path(output).resolve()
    manifest_path = output.with_suffix(output.suffix + ".meta.json")
    if output.exists() or manifest_path.exists():
        raise ValueError("Reproduction output already exists; choose a new output path")
    data = json.loads(report_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "1.0":
        raise ValueError("Unsupported report schema version")
    issue = next((i for i in data["issues"] if i["id"] == issue_id), None)
    if issue is None:
        raise ValueError(f"Issue not found: {issue_id}")
    if issue["rule"] == "INPUT_JSON":
        raise ValueError(
            "Invalid JSON cannot be reproduced as valid JSONL; use the reported source line directly"
        )
    refs = issue["related"] + [{"source": issue["source"], "record_sha256": issue["record_sha256"]}]
    raw = []
    for ref in refs:
        source = ref["source"]
        path = Path(source["path"])
        if not path.is_file():
            raise ValueError(f"Original input unavailable: {path}")
        record = next((r for r in read_records(path) if r.source.record == source["record"]), None)
        if record is None or record.sha256 != ref["record_sha256"]:
            raise ValueError(f"Source record changed since scanning: {path}, record {source['record']}")
        raw.append(record.raw)
    config = Config(**data["config"])
    checks = 0

    def persists(candidate: list) -> bool:
        nonlocal checks
        checks += 1
        result = scan_records(
            (Record(row, Source("<repro>", i + 1, i)) for i, row in enumerate(candidate)), config
        )
        return any(i.rule == issue["rule"] and i.source.record == len(candidate) - 1 for i in result.issues)

    if not persists(raw):
        raise ValueError("Original finding could not be replayed with this report's configuration")
    # Fixed-point deletion gives 1-minimal top-level fields and whole messages
    # when the budget completes. Token arrays remain intact to preserve alignment.
    complete = False
    while checks < max_checks:
        changed = False
        for ri in range(len(raw)):
            if not isinstance(raw[ri], dict):
                continue
            for key in list(raw[ri]):
                if checks >= max_checks:
                    break
                candidate = copy.deepcopy(raw)
                del candidate[ri][key]
                if persists(candidate):
                    raw, changed = candidate, True
            for key in ("messages", "conversations", "events"):
                index = 0
                while (
                    isinstance(raw[ri].get(key), list) and index < len(raw[ri][key]) and checks < max_checks
                ):
                    candidate = copy.deepcopy(raw)
                    del candidate[ri][key][index]
                    if persists(candidate):
                        raw, changed = candidate, True
                    else:
                        index += 1
        if not changed and checks < max_checks:
            complete = True
            break
    # A final replay is mandatory even when the minimization budget was exhausted.
    if not persists(raw):
        raise ValueError("Internal minimization verification failed")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False, allow_nan=True) + "\n" for row in raw), encoding="utf-8"
    )
    manifest = {
        "rule": issue["rule"],
        "original_issue": issue_id,
        "sources": refs,
        "config": asdict(config),
        "checks": checks,
        "verified": True,
        "minimization_complete": complete,
        "minimality": "1-minimal under top-level field and whole-message deletion; token arrays and nested values preserved"
        if complete
        else "budget-limited structural reduction",
        "data_warning": "Contains source data. Review for secrets and personal data before sharing.",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest
