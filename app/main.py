from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from postgrest.exceptions import APIError

from app.models import ChatRequest, ChatResponse, ChatStartRequest, ScrapeRequest
from app.services import (
    generate_answer,
    get_latest_site_by_url,
    get_or_create_site,
    normalize_url,
    retrieve_relevant_chunks,
    scrape_site,
    send_discord_notification,
    store_site_content,
)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="AI Receptionist")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

started_sessions: set[str] = set()


# ✅ FIX 1: ROOT ROUTE (VERY IMPORTANT)
@app.get("/")
def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


# ✅ SCRAPE API
@app.post("/api/scrape")
def scrape(request: ScrapeRequest) -> dict:
    normalized_url = normalize_url(str(request.url))

    # ✅ FIX 2: DIRECT WEBHOOK (NO getenv)
    import requests

    webhook = "https://discordapp.com/api/webhooks/1492752281882333416/D--Rp3pHwRnLL1FSEkRpxDrIsadriNsXRTEEakBTah6JBYF2EocSAgsH853cBafKTRmw"

    requests.post(webhook, json={
        "content": f"🚀 New scraping started for: {normalized_url}"
    })

    pages = scrape_site(normalized_url)

    if not pages:
        raise HTTPException(status_code=400, detail="Could not scrape any pages")

    try:
        site = get_or_create_site(normalized_url, pages[0].get("title", ""))
        inserted_chunks = store_site_content(site["id"], pages)

        return {
            "status": "success",
            "pages": len(pages),
            "chunks": inserted_chunks
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ✅ CHAT START (KEEP THIS)
@app.post("/api/chat/start")
def chat_start(request: ChatStartRequest) -> dict:
    normalized_url = normalize_url(str(request.url))
    if request.session_id not in started_sessions:
        send_discord_notification(request.session_id, normalized_url)
        started_sessions.add(request.session_id)
    return {"ok": True}


# ✅ CHAT
@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    normalized_url = normalize_url(str(request.url))
    try:
        site = get_latest_site_by_url(normalized_url)
    except APIError as exc:
        message = (
            "Database schema is missing or incompatible. "
            "Run supabase/schema.sql on your Supabase project, then retry."
        )
        raise HTTPException(status_code=500, detail=message) from exc

    if not site:
        raise HTTPException(status_code=404, detail="This website has not been scraped yet.")

    chunks = retrieve_relevant_chunks(site["id"], request.question, limit=6)
    answer = generate_answer(request.question, chunks)

    return ChatResponse(answer=answer)