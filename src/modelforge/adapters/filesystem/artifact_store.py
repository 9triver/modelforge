"""Local filesystem implementation of ArtifactStore protocol."""

from __future__ import annotations

import io
import shutil
from pathlib import Path
from typing import IO


class LocalArtifactStore:
    """Stores binary artifacts on the local filesystem.

    Keys are forward-slash separated paths interpreted relative to *base_path*.
    For example, key ``models/slug/versions/v1/weights/model.pkl`` maps to
    ``<base_path>/models/slug/versions/v1/weights/model.pkl``.
    """

    def __init__(self, base_path: Path) -> None:
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        return self.base_path / key

    def put(self, key: str, data: IO[bytes], metadata: dict[str, str] | None = None) -> str:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            shutil.copyfileobj(data, f)
        return key

    def get(self, key: str) -> IO[bytes]:
        path = self._resolve(key)
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {key}")
        return open(path, "rb")

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)

    def list_keys(self, prefix: str) -> list[str]:
        root = self._resolve(prefix)
        if not root.exists():
            return []
        keys = []
        if root.is_file():
            return [prefix]
        for p in sorted(root.rglob("*")):
            if p.is_file():
                keys.append(str(p.relative_to(self.base_path)))
        return keys

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    def copy(self, src_key: str, dst_key: str) -> None:
        src = self._resolve(src_key)
        dst = self._resolve(dst_key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)

    def get_local_path(self, key: str) -> Path | None:
        path = self._resolve(key)
        return path if path.exists() else None

    def copy_tree(self, src_key: str, dst_key: str) -> None:
        """Copy an entire directory tree (convenience for version copying)."""
        src = self._resolve(src_key)
        dst = self._resolve(dst_key)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    def remove_tree(self, key: str) -> None:
        """Remove an entire directory tree."""
        path = self._resolve(key)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)

    def put_bytes(self, key: str, data: bytes, metadata: dict[str, str] | None = None) -> str:
        """Convenience: store raw bytes."""
        return self.put(key, io.BytesIO(data), metadata)

    def get_bytes(self, key: str) -> bytes:
        """Convenience: read entire artifact as bytes."""
        with self.get(key) as f:
            return f.read()
