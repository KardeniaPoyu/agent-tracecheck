from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=True)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def finite_number(value: Any) -> bool:
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


@dataclass(frozen=True)
class Source:
    path: str = "<memory>"
    line: int = 1
    record: int = 0
    pointer: str = ""


@dataclass
class Record:
    raw: Any
    source: Source = field(default_factory=Source)
    parse_error: str | None = None

    @property
    def sha256(self) -> str:
        return digest(self.raw)


@dataclass
class Config:
    reward_min: float = 0.0
    reward_max: float = 1.0
    success_reward_min: float = 0.5
    failure_reward_max: float = 0.0
    ignore_index: int = -100
    train_roles: list[str] = field(default_factory=lambda: ["assistant"])
    require_final_assistant: bool = True
    disabled_rules: list[str] = field(default_factory=list)
    severity: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        from .rules import RULES

        for key in ("reward_min", "reward_max", "success_reward_min", "failure_reward_max"):
            if not finite_number(getattr(self, key)):
                raise ValueError(f"{key} must be a finite number")
        if self.reward_min > self.reward_max:
            raise ValueError("reward_min must not exceed reward_max")
        if not self.reward_min <= self.success_reward_min <= self.reward_max:
            raise ValueError("success_reward_min must be inside the reward range")
        if not self.reward_min <= self.failure_reward_max <= self.reward_max:
            raise ValueError("failure_reward_max must be inside the reward range")
        if type(self.ignore_index) is not int:
            raise ValueError("ignore_index must be an integer")
        if type(self.require_final_assistant) is not bool:
            raise ValueError("require_final_assistant must be a boolean")
        if (
            not isinstance(self.train_roles, list)
            or not self.train_roles
            or any(r not in {"assistant", "user", "system", "developer", "tool"} for r in self.train_roles)
        ):
            raise ValueError("train_roles must be a nonempty list of supported roles")
        if not isinstance(self.disabled_rules, list) or any(r not in RULES for r in self.disabled_rules):
            raise ValueError("disabled_rules contains an unknown rule")
        if not isinstance(self.severity, dict) or any(
            k not in RULES or v not in {"error", "warning", "info"} for k, v in self.severity.items()
        ):
            raise ValueError("severity must map known rules to error, warning, or info")


@dataclass
class Issue:
    id: str
    rule: str
    severity: str
    message: str
    source: Source
    pointer: str
    suggestion: str
    record_sha256: str
    related: list[dict] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Report:
    config: Config
    issues: list[Issue] = field(default_factory=list)
    records: int = 0
    files: int = 0

    def to_dict(self) -> dict:
        counts = {s: sum(i.severity == s for i in self.issues) for s in ("error", "warning", "info")}
        return {
            "schema_version": "1.0",
            "tool": {"name": "agent-tracecheck", "version": "0.1.0"},
            "config": asdict(self.config),
            "summary": {"files": self.files, "records": self.records, "issues": len(self.issues), **counts},
            "issues": [i.to_dict() for i in self.issues],
        }
