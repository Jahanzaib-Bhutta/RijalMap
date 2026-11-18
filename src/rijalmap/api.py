"""HTTP API and the web page.

Run from the project root:   python -m uvicorn rijalmap.api:app --reload   then open http://127.0.0.1:8000
"""
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from rijalmap.engine import HadithNotFound, IsnadGraphEngine
from rijalmap.repository import Repository

WEB_DIR = Path(__file__).resolve().parent / "web"
app = FastAPI(title="RijalMap", version="0.1")


@lru_cache
def get_repo() -> Repository:
    return Repository()


@app.get("/api/sources")
def sources(repo: Repository = Depends(get_repo)):
    """The books available in the database."""
    return {"sources": repo.list_sources()}


@app.get("/api/graph/entry/{entry_id}")
def graph_for_entry(entry_id: int, repo: Repository = Depends(get_repo)):
    """The chain of one dataset row (what a text-search result opens)."""
    engine = IsnadGraphEngine(repo)
    try:
        engine.build_graph_for_entry(entry_id)
    except HadithNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return engine.export_cytoscape_json()


@app.get("/api/graph/{source}/{hadith_no}")
def graph_for_number(source: str, hadith_no: str, repo: Repository = Depends(get_repo)):
    """All chains stored under one book + number, merged into one graph."""
    engine = IsnadGraphEngine(repo)
    try:
        engine.build_graph(source, hadith_no)
    except HadithNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return engine.export_cytoscape_json()


@app.get("/api/search")
def search(q: str = Query(..., min_length=3, max_length=200), source: str | None = None,
           limit: int = Query(15, ge=1, le=30), repo: Repository = Depends(get_repo)):
    """Full-text search over the English and Arabic hadith text."""
    return {"query": q, "results": repo.search_text(q.strip(), source or None, limit)}


@app.get("/api/narrator/{narrator_id}")
def narrator(narrator_id: int, repo: Repository = Depends(get_repo)):
    """One narrator's dictionary entry plus a sample of recorded teachers and students."""
    found = repo.get_narrators([narrator_id]).get(narrator_id)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Narrator {narrator_id} is not in the dictionary.")
    return {**asdict(found), "relations": repo.get_relations(narrator_id)}


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(WEB_DIR / "index.html")
