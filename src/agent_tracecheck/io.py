"""Streaming JSONL input; JSON arrays are loaded as a document."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator

from .model import Record, Source


def discover(paths: Iterable[str | Path]) -> list[Path]:
    found: dict[str, Path] = {}
    for item in paths:
        path = Path(item).expanduser().resolve()
        if not path.exists():
            raise ValueError(f"Input does not exist: {path}")
        candidates = sorted(path.rglob("*")) if path.is_dir() else [path]
        for candidate in candidates:
            if candidate.is_file() and (
                not path.is_dir() or candidate.suffix.lower() in {".json", ".jsonl", ".ndjson"}
            ):
                found[str(candidate.resolve())] = candidate.resolve()
    if not found:
        raise ValueError("No JSON or JSONL input files found")
    return sorted(found.values())


def read_records(path: str | Path) -> Iterator[Record]:
    path = Path(path).resolve()
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        with path.open("rb") as stream:
            index = 0
            for line, data in enumerate(stream, 1):
                if line == 1:
                    data = data.removeprefix(b"\xef\xbb\xbf")
                if not data.strip():
                    continue
                source = Source(str(path), line, index)
                index += 1
                try:
                    yield Record(json.loads(data.decode("utf-8")), source)
                except (ValueError, UnicodeError) as exc:
                    # Keep raw bytes as hex for stable fingerprints without losing bad input.
                    yield Record({"invalid_utf8_or_json_hex": data.hex()}, source, str(exc))
    else:
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (ValueError, UnicodeError) as exc:
            yield Record(None, Source(str(path), getattr(exc, "lineno", 1)), str(exc))
            return
        if isinstance(raw, list):
            for index, row in enumerate(raw):
                yield Record(row, Source(str(path), 1, index, f"/{index}"))
        elif isinstance(raw, dict) and isinstance(raw.get("trajectories"), list):
            for index, row in enumerate(raw["trajectories"]):
                yield Record(row, Source(str(path), 1, index, f"/trajectories/{index}"))
        else:
            yield Record(raw, Source(str(path)))


def write_json(path: str | Path, value: object) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
