# HUGE Inventory Tracker — Python + Supabase (Starter)

This is a beginner-friendly starter kit to build your inventory tracking app for HUGE Handyman.

## What you get
- **Streamlit web app** (`app.py`) — runs on desktop and mobile browsers
- **Supabase connection helper** (`lib/supabase_client.py`)
- **Database schema** (`sql/schema.sql`) — tables & basic policies
- **Requirements** (`requirements.txt`)
- **.env example** (`.env.example`)

---

## 1) Install Python and dependencies
- Install **Python 3.11+** from https://www.python.org/downloads/
- Open a terminal in this folder and run:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## 2) Create a Supabase project
- Go to https://supabase.com → New Project → pick a name (e.g., `huge_inventory`).
- In **Project Settings → API**, copy:
  - `Project URL`
  - `anon` public key (for client)
  - `service_role` key (for server-side scripts only)

> For the Streamlit app (runs server-side), you can use `SERVICE_ROLE_KEY` at first while you’re prototyping **but keep it private**. Don’t commit it to GitHub.

## 3) Create tables
- In Supabase → SQL Editor → paste **sql/schema.sql** and run it.
- Optional: insert sample data at the bottom of that file.

## 4) Configure environment
- Copy `.env.example` to `.env` and fill in your values from Supabase:

```
SUPABASE_URL=YOUR_URL_HERE
SUPABASE_ANON_KEY=YOUR_ANON_KEY_HERE
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY_HERE
APP_BRAND=HUGE Handyman
```

## 5) Run the app
```bash
streamlit run app.py
```
Open the local URL it prints (usually http://localhost:8501).

## 6) Next steps
- Replace the temporary “Admin Mode” checkbox with real auth (Supabase Auth)
- Add photos (Supabase Storage)
- Add QR/Barcode scanning (later)
- Deploy Streamlit to the cloud and connect to the same Supabase project

---

### Notes
- This starter keeps things simple on purpose. We’ll harden auth and row-level security in later steps.
- Only share the **anon** key in public apps. Keep the **service role** key secret.
"# huge-handyman-inventory" 
