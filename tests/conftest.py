from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from modelforge.main import app
from modelforge.store import ModelStore, get_store


@pytest.fixture
def store(tmp_path) -> ModelStore:
    return ModelStore(tmp_path)


@pytest.fixture
def client(store: ModelStore) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_store] = lambda: store
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
