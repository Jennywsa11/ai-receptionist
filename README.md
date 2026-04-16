# AI Receptionist Chatbot

FastAPI + Supabase + OpenAI app that scrapes a website, stores semantic vectors, and answers questions using only website data.

## Features

- Enter a website URL and scrape public pages (same domain).
- Chunk + embed content using OpenAI `text-embedding-3-small`.
- Store vectors in Supabase (`pgvector` / `vector` extension).
- Ask questions in a web chat UI.
- Retrieve relevant chunks via vector similarity search and answer with `gpt-4o-mini`.
- Fallback answer when info is not present:
  - `I can't find that info, please contact the business directly.`
- Sends Discord webhook notification when a chat session starts.

## Project structure

- `app/main.py` - FastAPI routes
- `app/services.py` - scraper, embeddings, Supabase, answer generation, Discord notifications
- `static/` - plain HTML/CSS/JS frontend
- `supabase/schema.sql` - database schema + vector match RPC

## 1) Supabase setup (pgvector)

1. Create a Supabase project.
2. Open SQL Editor in Supabase dashboard.
3. Run `supabase/schema.sql`.
4. This script:
   - Enables vector extension with `create extension if not exists vector;`
   - Creates `scraped_sites`
   - Creates `site_content` with `embedding vector(1536)`
   - Creates `match_site_content(...)` RPC function for semantic search

## 2) Environment variables

Copy `.env.example` to `.env` and fill:

- `OPENAI_API_KEY=YOUR_KEY`
- `SUPABASE_URL=YOUR_URL`
- `SUPABASE_KEY=YOUR_KEY`
- `DISCORD_WEBHOOK_URL=YOUR_WEBHOOK`
- `PORT=8000`

## 3) Run locally

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open [http://localhost:8000](http://localhost:8000)

## 4) Usage flow

1. Enter website URL and click **Scrape Website**.
2. Wait for scraping + embedding to finish.
3. Ask business questions in chat.
4. Answers are grounded on matching website chunks only.

## 5) Deploy to GitHub

```bash
git init
git add .
git commit -m "Initial AI receptionist chatbot"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/ai-receptionist.git
git push -u origin main
```

## 6) Deploy to Railway

1. Push code to GitHub.
2. In Railway, create **New Project** -> **Deploy from GitHub repo**.
3. Select your repository.
4. Add env vars from `.env` in Railway Variables tab.
5. Railway will use `Procfile`:
   - `web: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`
6. Deploy and open the generated Railway public URL.

## Notes

- App binds to `0.0.0.0` and reads `PORT` from environment for cloud deployment.
- Scraper currently follows same-domain links only and stores plain text content from each page.
