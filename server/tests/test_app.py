from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from soccer_wallart import app as app_module
from soccer_wallart.sample import sample_matches


class FakeProvider:
    def matches(self, slugs, start, end):
        return sample_matches(datetime.now(timezone.utc).replace(hour=12))

    def team_schedule(self, *a, **k):
        return []


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(app_module._svc, "provider", FakeProvider())
    app_module._memo.clear()
    return TestClient(app_module.app)


def test_frame_bin_and_304(client):
    r = client.get("/frame.bin")
    assert r.status_code == 200
    assert len(r.content) == 800 * 480 // 2
    etag = r.headers["etag"]
    assert int(r.headers["x-sleep-seconds"]) >= 15 * 60
    r2 = client.get("/frame.bin", headers={"If-None-Match": etag})
    assert r2.status_code == 304


def test_preview_and_gallery(client):
    r = client.get("/preview.png?scale=2")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert client.get("/gallery").status_code == 200
    assert client.get("/gallery/s1/deco.png").status_code == 200
    assert client.get("/gallery/s1/nope.png").status_code == 400


def test_board_json(client):
    j = client.get("/board.json").json()
    assert j["featured"] is not None
    assert len(j["upcoming"]) <= 5
