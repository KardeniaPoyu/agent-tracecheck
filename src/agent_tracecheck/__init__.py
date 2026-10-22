"""Public API for deterministic, local agent trajectory quality checks."""

from .engine import scan, scan_records
from .model import Config, Record, Source

__version__ = "0.1.0"
__all__ = ["Config", "Record", "Source", "scan", "scan_records"]
