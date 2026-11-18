"""API tests against the fixture database (see conftest.py)."""
import pytest
from fastapi.testclient import TestClient

from rijalmap.api import app, get_repo
from tests.conftest import needs_db

pytestmark = needs_db


@pytest.fixture()
def client(loaded):
    _, repo = loaded
    app.dependency_overrides[get_repo] = lambda: repo
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_sources(client):
    assert client.get("/api/sources").json() == {"sources": ["TEST Source"]}


def test_graph_by_number_has_colours_and_entries(client):
    body = client.get("/api/graph/TEST Source/2").json()
    assert {e["data"]["status"] for e in body["elements"]["edges"]} == {"contradicted", "not_recorded"}
    assert body["hadith"]["entries"][0]["hadith_no"] == "2"
    assert body["summary"]["links_by_status"]["contradicted"] == 1


def test_two_chains_merge_through_the_api(client):
    body = client.get("/api/graph/TEST Source/4").json()
    shared = {s["narrator_id"] for s in body["summary"]["shared_narrators"]}
    assert body["summary"]["chains"] == 2 and shared == {1, 2}


def test_unknown_number_is_404(client):
    r = client.get("/api/graph/TEST Source/999")
    assert r.status_code == 404 and "999" in r.json()["detail"]


def test_number_with_reused_dataset_id_is_flagged(client):
    flags = [e["number_suspect"] for e in client.get("/api/graph/TEST Source/6").json()["hadith"]["entries"]]
    assert flags == [True]
    assert client.get("/api/graph/TEST Source/1").json()["hadith"]["entries"][0]["number_suspect"] is False


def test_text_search_finds_hadith_whatever_its_number(client):
    results = client.get("/api/search", params={"q": "intentions"}).json()["results"]
    assert {r["hadith_no"] for r in results} == {"1", "4"}
    entry_id = results[0]["entry_id"]
    graph = client.get(f"/api/graph/entry/{entry_id}").json()
    assert graph["summary"]["chains"] == 1


def test_search_rules(client):
    assert client.get("/api/search", params={"q": "ab"}).status_code == 422          # too short
    assert client.get("/api/search", params={"q": "intentions", "source": "Nope"}).json()["results"] == []
    assert client.get("/api/search", params={"q": "zzzzqqqq"}).json()["results"] == []


def test_narrator_details(client):
    body = client.get("/api/narrator/3").json()
    assert body["birth_year_ah"] == -41 and body["relations"]["teachers"]["total"] == 2
    assert client.get("/api/narrator/777777").status_code == 404


def test_page_is_served(client):
    assert "RijalMap" in client.get("/").text
