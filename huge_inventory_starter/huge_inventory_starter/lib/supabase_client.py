from supabase import create_client, Client
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

def get_client(service: bool = True) -> Client:
    """Return a Supabase client.
    - service=True: uses service role (server-side scripts; full access). KEEP SECRET.
    - service=False: uses anon key (restricted by RLS; safer for public clients).
    """
    key = SUPABASE_SERVICE_ROLE_KEY if service else SUPABASE_ANON_KEY
    if not SUPABASE_URL or not key:
        raise RuntimeError("Missing SUPABASE_URL or API key. Check your .env file.")
    return create_client(SUPABASE_URL, key)
