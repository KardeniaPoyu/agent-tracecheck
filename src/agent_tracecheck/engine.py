from __future__ import annotations

import json
import sqlite3
import tempfile
import copy
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .adapters import semantic_messages
from .checks import check_record
from .io import discover, read_records
from .model import Config, Issue, Record, Report, Source, canonical, digest
from .rules import RULES


class DuplicateIndex:
    """Disk-backed dataset index: raw trajectory payloads are never stored here."""

    def __init__(self, path: str):
        self.db = sqlite3.connect(path)
        self.db.executescript("""
            CREATE TABLE samples (hash TEXT, supervision TEXT, split TEXT, task TEXT, ref TEXT);
            CREATE INDEX sample_hash ON samples(hash);
            CREATE INDEX sample_task ON samples(hash, task);
            CREATE INDEX sample_variant ON samples(hash, supervision, split, task);
            CREATE TABLE ids (id TEXT PRIMARY KEY, hash TEXT, ref TEXT);
        """)

    def check_id(self, record: Record, emit) -> None:
        raw = record.raw
        ref = {"source": asdict(record.source), "record_sha256": record.sha256}
        ref_json = canonical(ref)
        record_id = raw.get("id")
        if isinstance(record_id, str):
            previous = self.db.execute("SELECT hash, ref FROM ids WHERE id=?", (record_id,)).fetchone()
            if previous and previous[0] != record.sha256:
                emit(
                    "ID_COLLISION",
                    "/id",
                    "Record ID is already associated with different data.",
                    related=[json.loads(previous[1])],
                )
            if not previous:
                self.db.execute("INSERT INTO ids VALUES (?, ?, ?)", (record_id, record.sha256, ref_json))

    def check(self, record: Record, rows: list, emit) -> None:
        raw = record.raw
        ref_json = canonical({"source": asdict(record.source), "record_sha256": record.sha256})
        signature = digest(semantic_messages(rows))
        supervision = digest(
            {
                **{
                    k: raw.get(k)
                    for k in (
                        "reward",
                        "outcome",
                        "reward_components",
                        "input_ids",
                        "labels",
                        "loss_mask",
                        "attention_mask",
                        "token_roles",
                        "label_alignment",
                        "eos_token_id",
                    )
                },
                "weights": [m.data.get("weight", 1) for m in rows],
            }
        )
        split, task = raw.get("split"), raw.get("task_id")
        first = self.db.execute("SELECT ref FROM samples WHERE hash=? LIMIT 1", (signature,)).fetchone()
        if first:
            retry = (
                self.db.execute(
                    "SELECT ref FROM samples WHERE hash=? AND task=? LIMIT 1", (signature, task)
                ).fetchone()
                if task
                else None
            )
            emit(
                "RETRY_DUPLICATE" if retry else "DUPLICATE_SAMPLE",
                "",
                "Trajectory matches an earlier sample after tool-call ID normalization.",
                related=[json.loads((retry or first)[0])],
            )
            conflict = self.db.execute(
                "SELECT ref FROM samples WHERE hash=? AND supervision!=? LIMIT 1", (signature, supervision)
            ).fetchone()
            if conflict:
                emit(
                    "DUPLICATE_LABEL_CONFLICT",
                    "",
                    "Identical trajectory carries different supervision.",
                    related=[json.loads(conflict[0])],
                )
            leak = (
                self.db.execute(
                    "SELECT ref FROM samples WHERE hash=? AND split IS NOT NULL AND split!=? LIMIT 1",
                    (signature, split),
                ).fetchone()
                if split
                else None
            )
            if leak:
                emit(
                    "SPLIT_LEAKAGE",
                    "/split",
                    "Identical trajectory appears in a different dataset split.",
                    related=[json.loads(leak[0])],
                )
        # Retain distinct metadata variants, not one row for every identical retry.
        exists = self.db.execute(
            "SELECT 1 FROM samples WHERE hash=? AND supervision=? AND split IS ? AND task IS ?",
            (signature, supervision, split, task),
        ).fetchone()
        if not exists:
            self.db.execute(
                "INSERT INTO samples VALUES (?, ?, ?, ?, ?)", (signature, supervision, split, task, ref_json)
            )


def scan_records(records: Iterable[Record], config: Config | None = None) -> Report:
    config = copy.deepcopy(config or Config())
    config.validate()
    report = Report(config)
    paths = set()
    with tempfile.TemporaryDirectory(prefix="agent-tracecheck-") as tmp:
        index = DuplicateIndex(str(Path(tmp) / "index.sqlite3"))
        try:
            for record in records:
                report.records += int(not (record.parse_error and record.input_rule == "INPUT_EMPTY"))
                paths.add(record.source.path)
                observed = []

                def emit(rule, pointer, message, *, details=None, related=None):
                    observed.append(rule)
                    if rule in config.disabled_rules:
                        return
                    definition = RULES[rule]
                    issue_id = digest([asdict(record.source), record.sha256, rule, pointer])[:16]
                    report.issues.append(
                        Issue(
                            issue_id,
                            rule,
                            config.severity.get(rule, definition.severity),
                            message,
                            record.source,
                            pointer,
                            definition.suggestion,
                            record.sha256,
                            related or [],
                            details or {},
                        )
                    )

                if record.parse_error:
                    emit(record.input_rule, "", record.parse_error)
                    continue
                if isinstance(record.raw, dict):
                    index.check_id(record, emit)
                rows = check_record(record.raw, config, emit)
                # Malformed tool structures cannot be fingerprinted faithfully.
                blocked = {
                    "SCHEMA_RECORD",
                    "SCHEMA_MESSAGE",
                    "SCHEMA_FIELD",
                    "TOOL_CALL_FORMAT",
                    "TOOL_DUPLICATE_ID",
                    "TOOL_ORPHAN_RESULT",
                    "TOOL_LEGACY_FORMAT",
                    "TOOL_ARGUMENTS",
                }
                if rows and not blocked.intersection(observed):
                    index.check(record, rows, emit)
        finally:
            index.db.close()
    report.files = len(paths)
    if not paths:
        rule = RULES["INPUT_EMPTY"]
        if "INPUT_EMPTY" not in config.disabled_rules:
            report.issues.append(
                Issue(
                    digest(["INPUT_EMPTY"])[:16],
                    "INPUT_EMPTY",
                    config.severity.get("INPUT_EMPTY", rule.severity),
                    "Input contains no trajectories.",
                    Source(),
                    "",
                    rule.suggestion,
                    digest(None),
                )
            )
    return report


def scan(paths: Iterable[str | Path], config: Config | None = None) -> Report:
    files = discover(paths)
    report = scan_records((record for path in files for record in read_records(path)), config)
    report.files = len(files)
    return report
