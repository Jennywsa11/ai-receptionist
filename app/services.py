from __future__ import annotations

import json
import re
from collections import deque
from datetime import datetime, timezone
import math
from pathlib import Path
import sqlite3
import threading
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from postgrest.exceptions import APIError
from supabase import Client, create_client

from app import config

openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
_local_lock = threading.Lock()
_supabase_available = True
_local_db_path = Path(__file__).resolve().parent.parent / "data" / "fallback_store.db"


def _ensure_local_store() -> None:
    _local_db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_local_db_path)
    try:
        conn.execute(
            """
            create table if not exists scraped_sites (
              id integer primary key autoincrement,
              url text not null unique,
              title text,
              scraped_at text not null
            )
            """
        )
        conn.execute(
            """
            create table if not exists site_content (
              id integer primary key autoincrement,
              site_id integer not null,
              page_url text not null,
              content_chunk text not null,
              embedding text not null,
              created_at text not null,
              foreign key(site_id) references scraped_sites(id) on delete cascade
            )
            """
        )
        conn.execute("create index if not exists idx_site_content_site_id on site_content(site_id)")
        conn.commit()
    finally:
        conn.close()


_ensure_local_store()


def _mark_supabase_unavailable(exc: APIError) -> None:
    global _supabase_available
    _supabase_available = False
    print(f"Supabase unavailable, using local fallback store. Error: {exc}")


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _parse_embedding(raw: Any) -> list[float]:
    if isinstance(raw, list):
        return [float(v) for v in raw]
    if isinstance(raw, tuple):
        return [float(v) for v in raw]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            decoded = json.loads(text)
            if isinstance(decoded, list):
                return [float(v) for v in decoded]
        except json.JSONDecodeError:
            pass
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1]
        if not text:
            return []
        return [float(part.strip()) for part in text.split(",") if part.strip()]
    return []


def _local_get_site(url: str) -> dict[str, Any] | None:
    with _local_lock:
        conn = sqlite3.connect(_local_db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "select id, url, title, scraped_at from scraped_sites where url = ?",
                (url,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def _local_get_or_create_site(url: str, title: str) -> dict[str, Any]:
    with _local_lock:
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(_local_db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "select id, url, title, scraped_at from scraped_sites where url = ?",
                (url,),
            ).fetchone()
            if row:
                site_id = row["id"]
                conn.execute(
                    "update scraped_sites set title = ?, scraped_at = ? where id = ?",
                    (title or row["title"] or url, now_iso, site_id),
                )
                conn.execute("delete from site_content where site_id = ?", (site_id,))
                conn.commit()
                updated = conn.execute(
                    "select id, url, title, scraped_at from scraped_sites where id = ?",
                    (site_id,),
                ).fetchone()
                return dict(updated)

            cur = conn.execute(
                "insert into scraped_sites(url, title, scraped_at) values (?, ?, ?)",
                (url, title or url, now_iso),
            )
            site_id = cur.lastrowid
            conn.commit()
            created = conn.execute(
                "select id, url, title, scraped_at from scraped_sites where id = ?",
                (site_id,),
            ).fetchone()
            return dict(created)
        finally:
            conn.close()


def _local_insert_site_content(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    with _local_lock:
        conn = sqlite3.connect(_local_db_path)
        try:
            conn.executemany(
                """
                insert into site_content(site_id, page_url, content_chunk, embedding, created_at)
                values (?, ?, ?, ?, ?)
                """,
                [
                    (
                        row["site_id"],
                        row["page_url"],
                        row["content_chunk"],
                        json.dumps(row["embedding"]),
                        row["created_at"],
                    )
                    for row in rows
                ],
            )
            conn.commit()
            return len(rows)
        finally:
            conn.close()


def _local_retrieve_chunks(site_id: int, question_embedding: list[float], limit: int) -> list[dict[str, Any]]:
    with _local_lock:
        conn = sqlite3.connect(_local_db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                select id, site_id, page_url, content_chunk, embedding
                from site_content
                where site_id = ?
                """,
                (site_id,),
            ).fetchall()
        finally:
            conn.close()

    scored: list[dict[str, Any]] = []
    for row in rows:
        embedding = json.loads(row["embedding"])
        similarity = _cosine_similarity(embedding, question_embedding)
        scored.append(
            {
                "id": row["id"],
                "site_id": row["site_id"],
                "page_url": row["page_url"],
                "content_chunk": row["content_chunk"],
                "similarity": similarity,
            }
        )
    scored.sort(key=lambda item: item["similarity"], reverse=True)
    return scored[:limit]


def _supabase_retrieve_chunks_without_rpc(
    site_id: Any, question_embedding: list[float], limit: int
) -> list[dict[str, Any]]:
    res = (
        supabase.table("site_content")
        .select("id,site_id,page_url,content_chunk,embedding")
        .eq("site_id", site_id)
        .execute()
    )
    rows = res.data or []
    scored: list[dict[str, Any]] = []
    for row in rows:
        embedding = _parse_embedding(row.get("embedding"))
        similarity = _cosine_similarity(embedding, question_embedding)
        scored.append(
            {
                "id": row.get("id"),
                "site_id": row.get("site_id"),
                "page_url": row.get("page_url", ""),
                "content_chunk": row.get("content_chunk", ""),
                "similarity": similarity,
            }
        )
    scored.sort(key=lambda item: item["similarity"], reverse=True)
    return scored[:limit]


def get_latest_site_by_url(url: str) -> dict[str, Any] | None:
    normalized = normalize_url(url)
    if _supabase_available:
        try:
            site_res = (
                supabase.table("scraped_sites")
                .select("*")
                .eq("url", normalized)
                .order("scraped_at", desc=True)
                .limit(1)
                .execute()
            )
            if site_res.data:
                return site_res.data[0]
            return None
        except APIError as exc:
            _mark_supabase_unavailable(exc)

    return _local_get_site(normalized)


def normalize_url(raw_url: str) -> str:
    parsed = urlparse(raw_url.strip())
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    normalized = parsed._replace(netloc=netloc, path=path, params="", query="", fragment="")
    return urlunparse(normalized)


def scrape_site(start_url: str, max_pages: int | None = None) -> list[dict[str, str]]:
    max_pages = max_pages or config.MAX_PAGES
    start = normalize_url(start_url)
    parsed_start = urlparse(start)
    base_domain = parsed_start.netloc

    visited: set[str] = set()
    queue: deque[str] = deque([start])
    pages: list[dict[str, str]] = []

    headers = {"User-Agent": "AI-Receptionist-Bot/1.0 (+https://github.com)"}

    while queue and len(visited) < max_pages:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        try:
            response = requests.get(current, timeout=12, headers=headers)
            if response.status_code >= 400:
                continue
        except requests.RequestException:
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        title = (soup.title.string.strip() if soup.title and soup.title.string else "").strip()
        main_tag = soup.find("main") or soup.find("article") or soup.body
        text = main_tag.get_text(" ", strip=True) if main_tag else ""
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            pages.append({"url": current, "title": title, "content": text})

        for link in soup.find_all("a", href=True):
            absolute = normalize_url(urljoin(current, link["href"]))
            parsed_link = urlparse(absolute)
            if parsed_link.scheme not in {"http", "https"}:
                continue
            if parsed_link.netloc != base_domain:
                continue
            if absolute not in visited and absolute not in queue:
                queue.append(absolute)

    return pages


def chunk_text(text: str, max_chars: int | None = None, overlap: int | None = None) -> list[str]:
    max_chars = max_chars or config.MAX_CHARS_PER_CHUNK
    overlap = overlap or config.CHUNK_OVERLAP
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks


def embed_text(text: str) -> list[float]:
    res = openai_client.embeddings.create(model="text-embedding-3-small", input=text)
    return res.data[0].embedding


def get_or_create_site(url: str, title: str = "") -> dict[str, Any]:
    normalized = normalize_url(url)
    if _supabase_available:
        try:
            existing = (
                supabase.table("scraped_sites")
                .select("*")
                .eq("url", normalized)
                .order("scraped_at", desc=True)
                .limit(1)
                .execute()
            )

            if existing.data:
                site = existing.data[0]
                supabase.table("site_content").delete().eq("site_id", site["id"]).execute()
                updated = (
                    supabase.table("scraped_sites")
                    .update(
                        {
                            "title": title or site.get("title") or normalized,
                            "scraped_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    .eq("id", site["id"])
                    .execute()
                )
                return updated.data[0]

            created = (
                supabase.table("scraped_sites")
                .insert(
                    {
                        "url": normalized,
                        "title": title or normalized,
                        "scraped_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                .execute()
            )
            return created.data[0]
        except APIError as exc:
            _mark_supabase_unavailable(exc)

    return _local_get_or_create_site(normalized, title)


def store_site_content(site_id: int, pages: list[dict[str, str]]) -> int:
    inserted = 0
    rows: list[dict[str, Any]] = []

    for page in pages:
        chunks = chunk_text(page["content"])
        for chunk in chunks:
            rows.append(
                {
                    "site_id": site_id,
                    "page_url": page["url"],
                    "content_chunk": chunk,
                    "embedding": embed_text(chunk),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )

            if _supabase_available and len(rows) >= 30:
                try:
                    supabase.table("site_content").insert(rows).execute()
                    inserted += len(rows)
                    rows = []
                except APIError as exc:
                    _mark_supabase_unavailable(exc)

    if rows and _supabase_available:
        try:
            supabase.table("site_content").insert(rows).execute()
            inserted += len(rows)
            rows = []
        except APIError as exc:
            _mark_supabase_unavailable(exc)

    if rows:
        inserted += _local_insert_site_content(rows)

    return inserted


def retrieve_relevant_chunks(site_id: int, question: str, limit: int = 6) -> list[dict[str, Any]]:
    question_embedding = embed_text(question)
    if _supabase_available:
        try:
            res = supabase.rpc(
                "match_site_content",
                {"p_site_id": site_id, "query_embedding": question_embedding, "match_count": limit},
            ).execute()
            if res.data:
                return res.data
            # Some Supabase schemas use UUID site IDs or don't have the RPC.
            # Fall back to direct table retrieval + local cosine scoring.
            return _supabase_retrieve_chunks_without_rpc(site_id, question_embedding, limit)
        except APIError as exc:
            # Try non-RPC retrieval first when RPC signature/schema differs.
            try:
                return _supabase_retrieve_chunks_without_rpc(site_id, question_embedding, limit)
            except APIError:
                _mark_supabase_unavailable(exc)

    return _local_retrieve_chunks(site_id, question_embedding, limit)


def generate_answer(question: str, chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "I can't find that info, please contact the business directly."

    context_lines = []
    for item in chunks:
        page_url = item.get("page_url", "")
        content = item.get("content_chunk", "")
        context_lines.append(f"Source: {page_url}\n{content}")

    context = "\n\n".join(context_lines)
    prompt = (
        "You are an AI receptionist for this business.\n"
        "Answer only with facts from the provided website context.\n"
        "If the answer is not clearly present, respond exactly with:\n"
        "\"I can't find that info, please contact the business directly.\"\n\n"
        f"Question: {question}\n\n"
        f"Website Context:\n{context}"
    )

    completion = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.1,
        messages=[
            {
                "role": "system",
                "content": "You are strict about only using supplied website context.",
            },
            {"role": "user", "content": prompt},
        ],
    )

    answer = completion.choices[0].message.content or ""
    answer = answer.strip()
    if not answer:
        return "I can't find that info, please contact the business directly."
    return answer


def send_discord_notification(session_id: str, site_url: str) -> None:
    if not config.DISCORD_WEBHOOK_URL:
        return

    payload = {
        "content": (
            "New AI Receptionist chat session started\n"
            f"Session: `{session_id}`\n"
            f"Website: {normalize_url(site_url)}"
        )
    }
    try:
        resp = requests.post(config.DISCORD_WEBHOOK_URL, json=payload, timeout=8)
        # Discord webhooks typically return 204 No Content on success.
        if resp.status_code >= 400:
            # Avoid crashing user flows, but make failure visible in server logs.
            print(
                "Discord webhook failed:",
                resp.status_code,
                (resp.text or "").strip()[:500],
            )
    except requests.RequestException:
        # Keep the app working even if Discord is down/misconfigured.
        print("Discord webhook request failed (network/timeout).")
