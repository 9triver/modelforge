"""Tests for materialize_lfs (LFS pointer → real file substitution)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from modelforge import config, lfs_store, repo_reader


def _write_object(data: bytes) -> str:
    oid = hashlib.sha256(data).hexdigest()
    lfs_store.write(oid, data)
    return oid


def _make_pointer(oid: str, size: int) -> bytes:
    return (
        f"version https://git-lfs.github.com/spec/v1\n"
        f"oid sha256:{oid}\n"
        f"size {size}\n"
    ).encode()


def test_materialize_replaces_pointers(tmp_path):
    config.reset_settings(data_dir=tmp_path / "lfs-home")

    blob = b"hello-lfs-" * 1000  # ~10KB
    oid = _write_object(blob)

    checkout = tmp_path / "checkout"
    checkout.mkdir()
    ptr_path = checkout / "weights.bin"
    ptr_path.write_bytes(_make_pointer(oid, len(blob)))

    # 正常文件（非指针）不应被动
    normal = checkout / "README.md"
    normal.write_text("# hi")

    n = repo_reader.materialize_lfs(checkout)
    assert n == 1
    assert ptr_path.read_bytes() == blob
    assert normal.read_text() == "# hi"

    config.reset_settings()


def test_missing_object_raises(tmp_path):
    config.reset_settings(data_dir=tmp_path / "lfs-home")
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    # 指针指向一个未上传的 oid
    fake_oid = "0" * 64
    (checkout / "x.bin").write_bytes(_make_pointer(fake_oid, 123))

    try:
        repo_reader.materialize_lfs(checkout)
    except FileNotFoundError as e:
        assert fake_oid in str(e)
    else:
        raise AssertionError("expected FileNotFoundError")
    finally:
        config.reset_settings()
