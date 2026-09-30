"""Fixtures for API tests: an isolated data directory and a quiet app (no background workers)."""

from __future__ import annotations

import logging
import warnings

import pytest

warnings.filterwarnings("ignore", message=".*httpx.*")

from fastapi.testclient import TestClient  # noqa: E402

from server.app import create_app  # noqa: E402
from server.settings import Settings  # noqa: E402

logging.getLogger("httpx").setLevel(logging.WARNING)


def make_settings(tmp_path, **kw) -> Settings:
    base = dict(data_dir=tmp_path, background=False, preset="demo", seed=None, api_key=None,
                heavy_rate_capacity=10_000, heavy_rate_refill=1_000, autostart_traffic=False,
                web_dist=tmp_path / "no-web-build")
    base.update(kw)
    return Settings.from_env(**base)


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("qveris")


@pytest.fixture(scope="module")
def client(data_dir):
    app = create_app(make_settings(data_dir))
    with TestClient(app) as c:
        r = c.post("/api/v1/detection/baselines/calibrate", json={})
        assert r.status_code == 200
        yield c
