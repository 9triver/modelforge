"""Test PipelineRunner warm-start override support."""

import time
from unittest.mock import patch

import yaml

from modelforge.runner import PipelineRunner


def _setup_version(store, model_id, slug):
    """Create a minimal model + version + pipeline for runner testing."""
    model_dir = store.base_path / "models" / slug
    vdir = model_dir / "versions" / "v1.0.0"

    for d in ("code", "weights", "datasets", "features", "params"):
        (vdir / d).mkdir(parents=True)

    # Training script
    (vdir / "code" / "train.py").write_text(
        'import json, argparse\n'
        'p = argparse.ArgumentParser()\n'
        'p.add_argument("--dataset", default="")\n'
        'p.add_argument("--features", default="")\n'
        'p.add_argument("--params", default="")\n'
        'p.add_argument("--output", default="")\n'
        'p.add_argument("--warm-start", default="",'
        ' dest="warm_start")\n'
        'args = p.parse_args()\n'
        'print("warm_start=" + args.warm_start)\n'
        'json.dump({"mae": 1.0}, open("metrics.json","w"))\n'
    )

    (vdir / "weights" / "model.joblib").write_bytes(b"fake")
    (vdir / "datasets" / "train.csv").write_text("a,b\n1,2\n")
    (vdir / "features" / "features.yaml").write_text(
        "features: []\ntarget: b\n"
    )
    (vdir / "params" / "params.yaml").write_text("parameters: {}\n")

    (vdir / "version.yaml").write_text(yaml.dump({
        "id": "v1-id",
        "version": "1.0.0",
        "stage": "development",
        "file_path": "weights/model.joblib",
        "file_format": "joblib",
    }))

    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "model.yaml").write_text(yaml.dump({
        "id": model_id,
        "name": "test-model",
        "slug": slug,
    }))

    (model_dir / "pipeline.yaml").write_text(yaml.dump({
        "data_prep": {
            "dataset": "train.csv",
            "feature_config": "features.yaml",
        },
        "training": {
            "script": "train.py",
            "params": "params.yaml",
        },
        "output": {"format": "joblib"},
    }))

    # Rebuild index so store can find this model by id
    store._rebuild_index()

    return vdir


def _wait_for_run(store, model_id, run_id):
    for _ in range(50):
        r = store.get_run(model_id, run_id)
        if r["status"] in ("success", "failed"):
            return r
        time.sleep(0.1)
    return store.get_run(model_id, run_id)


class FakeProc:
    returncode = 0
    stdout = iter(["training done\n"])

    def wait(self):
        pass


def test_warm_start_in_command(store):
    """warm_start override adds --warm-start flag."""
    model_id = "test-model-id"
    slug = "test-model"
    _setup_version(store, model_id, slug)

    runner = PipelineRunner(store)
    captured_cmd = []

    def mock_popen(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return FakeProc()

    # Keep patch alive while background thread runs
    with patch("subprocess.Popen", side_effect=mock_popen):
        run = runner.start_run(
            model_id,
            base_version="v1.0.0",
            overrides={"warm_start": "model.joblib"},
        )
        _wait_for_run(store, model_id, run["id"])

    assert "--warm-start" in captured_cmd
    idx = captured_cmd.index("--warm-start")
    assert captured_cmd[idx + 1] == "weights/model.joblib"


def test_no_warm_start_without_override(store):
    """Without warm_start override, no --warm-start flag."""
    model_id = "test-model-id2"
    slug = "test-model2"
    _setup_version(store, model_id, slug)

    runner = PipelineRunner(store)
    captured_cmd = []

    def mock_popen(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return FakeProc()

    with patch("subprocess.Popen", side_effect=mock_popen):
        run = runner.start_run(
            model_id,
            base_version="v1.0.0",
        )
        _wait_for_run(store, model_id, run["id"])

    assert "--warm-start" not in captured_cmd
