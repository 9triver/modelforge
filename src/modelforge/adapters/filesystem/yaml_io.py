"""Thread-safe YAML and JSONL I/O helpers.

Shared by MetadataStore, LineageStore, and other filesystem adapters.
"""

from __future__ import annotations

import fcntl
import json
from pathlib import Path

import yaml


class YAMLFile:
    """Thread-safe YAML file reader/writer with advisory file locking."""

    @staticmethod
    def read(path: Path) -> dict | list:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                return yaml.safe_load(f) or {}
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    @staticmethod
    def write(path: Path, data: dict | list) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".yaml.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        tmp_path.replace(path)


class JSONLFile:
    """Append-only JSONL file for prediction logs."""

    @staticmethod
    def append(path: Path, record: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with open(path, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(line)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    @staticmethod
    def read_all(path: Path) -> list[dict]:
        if not path.exists():
            return []
        records = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    @staticmethod
    def write_all(path: Path, records: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".jsonl.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                for record in records:
                    f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        tmp_path.replace(path)
