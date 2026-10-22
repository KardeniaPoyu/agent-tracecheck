"""Strict JSON decoding, streaming JSONL, and gzip input support."""

from __future__ import annotations

import fnmatch
import gzip
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Iterable, Iterator

from .model import Record, Source


def strict_json(text: str):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key!r}")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"Nonstandard JSON number: {value}")

    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("JSON number exceeds the finite floating-point range")
        return result

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant, parse_float=number)


def discover(paths: Iterable[str | Path], exclude: Iterable[str] = ()) -> list[Path]:
    found: dict[str, Path] = {}
    patterns = tuple(exclude)
    extensions = (".json", ".jsonl", ".ndjson", ".json.gz", ".jsonl.gz", ".ndjson.gz")
    for item in paths:
        path = Path(item).expanduser().resolve()
        if not path.exists():
            raise ValueError(f"Input does not exist: {path}")
        candidates = sorted(path.rglob("*")) if path.is_dir() else [path]
        for candidate in candidates:
            relative = candidate.relative_to(path).as_posix() if path.is_dir() else candidate.name
            if any(fnmatch.fnmatchcase(relative, pattern) for pattern in patterns):
                continue
            if candidate.is_file() and (not path.is_dir() or candidate.name.lower().endswith(extensions)):
                found[str(candidate.resolve())] = candidate.resolve()
    if not found:
        raise ValueError("No JSON or JSONL input files found")
    return sorted(found.values())


def read_records(path: str | Path) -> Iterator[Record]:
    path = Path(path).resolve()
    compressed = path.suffix.lower() == ".gz"
    suffix = Path(path.stem).suffix.lower() if compressed else path.suffix.lower()
    opener = gzip.open if compressed else open
    if suffix in {".jsonl", ".ndjson"}:
        with opener(path, "rb") as stream:
            index = 0
            for line, data in enumerate(stream, 1):
                if line == 1:
                    data = data.removeprefix(b"\xef\xbb\xbf")
                if not data.strip():
                    continue
                source = Source(str(path), line, index)
                index += 1
                try:
                    yield Record(strict_json(data.decode("utf-8")), source)
                except (ValueError, UnicodeError, RecursionError) as exc:
                    yield Record({"invalid_utf8_or_json_hex": data.hex()}, source, str(exc))
            if index == 0:
                yield Record(None, Source(str(path)), "Input contains no trajectories.", "INPUT_EMPTY")
    else:
        try:
            with opener(path, "rt", encoding="utf-8-sig") as stream:
                raw = strict_json(stream.read())
        except (ValueError, UnicodeError, RecursionError) as exc:
            yield Record(None, Source(str(path), getattr(exc, "lineno", 1)), str(exc))
            return
        if isinstance(raw, list):
            rows, prefix = raw, ""
        elif isinstance(raw, dict) and isinstance(raw.get("trajectories"), list):
            rows, prefix = raw["trajectories"], "/trajectories"
        else:
            yield Record(raw, Source(str(path)))
            return
        if not rows:
            yield Record(
                None, Source(str(path), pointer=prefix), "Input contains no trajectories.", "INPUT_EMPTY"
            )
        for index, row in enumerate(rows):
            yield Record(row, Source(str(path), 1, index, f"{prefix}/{index}"))


def write_json(path: str | Path, value: object) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def atomic_write_text(path: str | Path, text: str) -> None:
    """Replace a complete report only after its temporary file is written."""
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
