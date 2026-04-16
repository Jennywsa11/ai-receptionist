import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
# Back-compat: earlier modules used DISCORD_WEBHOOK in .env
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "") or os.getenv("DISCORD_WEBHOOK", "")
PORT = int(os.getenv("PORT", "8000"))
MAX_PAGES = int(os.getenv("MAX_PAGES", "20"))
MAX_CHARS_PER_CHUNK = int(os.getenv("MAX_CHARS_PER_CHUNK", "1200"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
