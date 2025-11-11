# app.py — HUGE Handyman Inventory (Google Sheets backend)
# Data lives in your Google Spreadsheet (durable).
# - Tools by category with availability
# - Holder name(s) shown next to "Unavailable"
# - Only holder (or admin) can Check In
# - Text-entry categories ("Extra Material", "Bags / Accessories")
# - Admin: add/update tools, manage employees
# Secrets expected in Streamlit Cloud:
#   GOOGLE_CREDENTIALS = """{...full service-account JSON...}"""
#   SHEETS_ID = "your_sheet_id"
#   TOOLS_SHEET = "tools"
#   ROSTER_SHEET = "roster"
#   TX_SHEET     = "transactions"
#   EXTRA_SHEET  = "extra_material"
#   BAGS_SHEET   = "bags_accessories"
#   ADMIN_PASSWORD = "YourStrongPassword"   (optional; defaults to 'admin')

import json
import uuid
from datetime import datetime
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --------------------- UI / THEME ---------------------
APP_BRAND = "HUGE Handyman"
HUGE_BLUE = "#0a4d8c"
OK_GREEN = "#16a34a"
BAD_RED = "#dc2626"

st.set_page_config(page_title=f"{APP_BRAND} — Inventory", layout="wide")
st.markdown(
    f"""
    <style>
      .chip {{display:inline-block;padding:4px 10px;border-radius:999px;color:#fff;font-weight:700;font-size:12px}}
      .ok {{background:{OK_GREEN}}}
      .bad {{background:{BAD_RED}}}
      .muted {{color:#777}}
      .tool-card {{border:1px solid #eee;border-radius:12px;padding:12px;margin-bottom:10px;background:#fff}}
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------- SECRETS -------------------------
SECRETS = st.secrets
ADMIN_PASSWORD = SECRETS.get("ADMIN_PASSWORD", "admin")

SHEETS_ID = SECRETS.get("SHEETS_ID", "")
TOOLS_SHEET = SECRETS.get("TOOLS_SHEET", "tools")
ROSTER_SHEET = SECRETS.get("ROSTER_SHEET", "roster")
TX_SHEET     = SECRETS.get("TX_SHEET", "transactions")
EXTRA_SHEET  = SECRETS.get("EXTRA_SHEET", "extra_material")
BAGS_SHEET   = SECRETS.get("BAGS_SHEET", "bags_accessories")

# ----------------- GOOGLE AUTH / CLIENT ----------------
def get_gc():
    creds_dict = json.loads(SECRETS["GOOGLE_CREDENTIALS"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(credentials)

gc = get_gc()
sh = gc.open_by_key(SHEETS_ID)

ws_tools = sh.worksheet(TOOLS_SHEET)
ws_roster = sh.worksheet(ROSTER_SHEET)
ws_tx = sh.worksheet(TX_SHEET)
ws_extra = sh.worksheet(EXTRA_SHEET)
ws_bags = sh.worksheet(BAGS_SHEET)

# ----------------- HELPERS (SHEETS <-> DF) --------------
def ws_to_df(ws):
    data = ws.get_all_records()
    return pd.DataFrame(data)

def df_to_ws(df, ws):
    headers = list(df.columns)
    values = [headers] + df.astype(str).values.tolist()
    ws.clear()
    ws.update(values)

def append_row(ws, row_dict):
    headers = ws.row_values(1)
    ordered = [row_dict.get(h, "") for h in headers]
    ws.append_row(ordered, value_input_option="RAW")

def ensure_headers(ws, expected):
    hdr = ws.row_values(1)
    if hdr != expected:
        ws.clear()
        ws.update([expected])

# ----------------- ENSURE HEADERS EXIST ------------------
ensure_headers(ws_tools, ["name","category","quantity","current_out"])
ensure_headers(ws_roster, ["name","pin"])
ensure_headers(ws_tx, ["ts","user","action","item","qty","notes"])
ensure_headers(ws_extra, ["ts","user","entry"])
ensure_headers(ws_bags, ["ts","user","entry"])

# ----------------- DOMAIN: TOOLS -------------------------
def load_tools() -> pd.DataFrame:
    df = ws_to_df(ws_tools)
    if df.empty:
        return pd.DataFrame(columns=["name","category","quantity","current_out"])
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0).astype(int)
    df["current_out"] = pd.to_numeric(df["current_out"], errors="coerce").fillna(0).astype(int)
    return df

def upsert_tool(name: str, category: str, qty: int):
    df = load_tools()
    mask = (df["name"].str.lower() == name.strip().lower()) & (df["category"] == category)
    if mask.any():
        df.loc[mask, "quantity"] = int(qty)
    else:
        df.loc[len(df)] = [name.strip(), category, int(qty), 0]
    df_to_ws(df, ws_tools)

def delete_tool(name: str, category: str):
    df = load_tools()
    df = df[~((df["name"].str.lower()==name.strip().lower()) & (df["category"]==category))]
    df_to_ws(df, ws_tools)

# ----------------- DOMAIN: ROSTER ------------------------
def load_roster() -> pd.DataFrame:
    df = ws_to_df(ws_roster)
    if df.empty:
        df = pd.DataFrame([{"name":"Guest","pin":""}])
        df_to_ws(df, ws_roster)
    return df

def save_roster(df: pd.DataFrame):
    df = df[["name","pin"]]
    df_to_ws(df, ws_roster)

# ----------------- DOMAIN: TRANSACTIONS ------------------
def append_tx(ts: str, user: str, action: str, item: str, qty: int, notes: str=""):
    append_row(ws_tx, {
        "ts": ts, "user": user, "action": action, "item": item, "qty": str(qty), "notes": notes
    })

def load_tx() -> pd.DataFrame:
    df = ws_to_df(ws_tx)
    if df.empty:
        return pd.DataFrame(columns=["ts","user","action","item","qty","notes"])
    return df

def tool_key(name: str, category: str) -> str:
    # Use a stable key so same name in different categories is unique
    return f"{name} [{category}]"

def current_holders(key: str) -> list[str]:
    df = load_tx()
    if df.empty:
        return []
    sub = df[df["item"].astype(str) == key]
    if sub.empty:
        return []
    pvt = sub.pivot_table(index="user", columns="action", aggfunc="size", fill_value=0)
    outs = pvt["check_out"] if "check_out" in pvt.columns else 0
    ins  = pvt["check_in"]  if "check_in"  in pvt.columns else 0
    net = outs - ins
    holders = []
    if hasattr(net, "items"):
        for u, n in net.items():
            if n > 0:
                holders.extend([str(u)] * int(n))
    return holders

def available_count(quantity: int, holders: list[str]) -> int:
    return max(int(quantity) - len(holders), 0)

def sync_current_out_in_tools():
    df = load_tools()
    changed = False
    for idx, row in df.iterrows():
        key = tool_key(row["name"], row["category"])
        holders = current_holders(key)
        new_out = len(holders)
        if int(row.get("current_out", 0)) != new_out:
            df.at[idx, "current_out"] = new_out
            changed = True
    if changed:
        df_to_ws(df, ws_tools)

# ----------------- DOMAIN: TEXT LOGS ---------------------
def append_text_log(which: str, user: str, entry: str):
    ws = ws_extra if which == "Extra Material" else ws_bags
    append_row(ws, {"ts": datetime.now().isoformat(timespec="seconds"), "user": user, "entry": entry.strip()})

def load_text_log(which: str) -> pd.DataFrame:
    ws = ws_extra if which == "Extra Material" else ws_bags
    return ws_to_df(ws)

# ----------------- SESSION ------------------------------
if "is_admin" not in st.session_state:
    st.session_state["is_admin"] = False
if "current_user" not in st.session_state:
    st.session_state["current_user"] = ""

# ----------------- SIDEBAR ------------------------------
with st.sidebar:
    st.header(APP_BRAND)

    roster_df = load_roster()
    names = ["—"] + sorted(roster_df["name"].astype(str).tolist())
    sel = st.selectbox("Select your name", names, index=0)
    typed = st.text_input("Or type your name")
    chosen = typed.strip() or ("" if sel=="—" else sel)
    st.session_state["current_user"] = chosen
    st.caption(f"Logged in as: **{st.session_state['current_user'] or 'Guest'}**")

    st.divider()
    st.subheader("Admin Login")
    pw = st.text_input("Password", type="password")
    c1, c2 = st.columns(2)
    if c1.button("Login"):
        if pw == ADMIN_PASSWORD:
            st.session_state["is_admin"] = True
            st.success("Admin mode enabled")
            st.experimental_rerun()
        else:
            st.error("Wrong password")
    if c2.button("Logout"):
        st.session_state["is_admin"] = False
        st.experimental_rerun()

# ----------------- CATEGORIES ---------------------------
TOOL_CATEGORIES = [
    "Power Tools","Hand Tools","Ladders","Extension Cords",
    "Masking & Protection","Batteries","Blankets & Drop Cloths"
]
TEXT_CATEGORIES = ["Extra Material","Bags / Accessories"]
ALL_CATEGORIES = TOOL_CATEGORIES + TEXT_CATEGORIES

st.markdown("### Tool Inventory")
cat = st.radio("Select Category:", ALL_CATEGORIES, horizontal=True)

# Keep the current_out column synced with transactions
sync_current_out_in_tools()

# ----------------- TEXT CATEGORIES VIEW -----------------
if cat in TEXT_CATEGORIES:
    st.subheader(cat)
    with st.form(f"form_{cat.replace(' ','_')}"):
        entry = st.text_input("Describe what you’re taking", placeholder="e.g., 1 Milwaukee bag with 2 fine tool blades")
        submitted = st.form_submit_button("Submit")
        if submitted:
            user = st.session_state.get("current_user","").strip()
            if not user:
                st.warning("Pick your name first (sidebar).")
            elif not entry.strip():
                st.warning("Please type something.")
            else:
                append_text_log(cat, user, entry)
                st.success("Logged.")
                st.experimental_rerun()

    logs = load_text_log(cat)
    if logs.empty:
        st.info("No entries yet.")
    else:
        st.dataframe(logs.sort_values("ts", ascending=False), use_container_width=True)

# ----------------- TOOL CATEGORIES VIEW -----------------
else:
    st.subheader(cat)
    is_admin = bool(st.session_state["is_admin"])
    tools = load_tools()
    cat_df = tools[tools["category"] == cat].copy()

    # Admin add/update
    if is_admin:
        st.markdown("**Admin — Add or Update**")
        a1, a2, a3 = st.columns([5,2,2])
        with a1:
            nm = st.text_input("Item name", key="new_tool_nm")
        with a2:
            qty = st.number_input("Quantity", min_value=0, step=1, value=0, key="new_tool_qty")
        with a3:
            st.write("")
            if st.button("Save to selected category", use_container_width=True):
                if not nm.strip():
                    st.warning("Enter a name.")
                else:
                    upsert_tool(nm, cat, int(qty))
                    st.success("Saved.")
                    st.experimental_rerun()

    if cat_df.empty:
        st.info("No items found for this category.")
    else:
        cat_df = cat_df.sort_values("name", key=lambda s: s.str.lower())
        for _, row in cat_df.iterrows():
            k = tool_key(row["name"], row["category"])
            holders = current_holders(k)
            avail = available_count(int(row["quantity"]), holders)

            with st.container():
                st.markdown('<div class="tool-card">', unsafe_allow_html=True)
                st.markdown(f"**{row['name']}**")

                if avail > 0:
                    st.markdown(
                        f"<span class='chip ok'>Available</span> "
                        f"<span class='muted'>&nbsp;({avail} of {row['quantity']})</span>",
                        unsafe_allow_html=True
                    )
                else:
                    holder_names = ", ".join(sorted(set(holders))) if holders else "—"
                    st.markdown(
                        f"<span class='chip bad'>Unavailable</span> &nbsp;"
                        f"Holder: **{holder_names}** "
                        f"<span class='muted'>(total {row['quantity']})</span>",
                        unsafe_allow_html=True
                    )

                c1, c2, c3 = st.columns([1,1,2])
                user = st.session_state.get("current_user","").strip() or "Guest"

                with c1:
                    can_out = (avail > 0) and (user and user.lower() != "guest")
                    if st.button("Check Out", key=f"out_{row['name']}_{row['category']}", disabled=not can_out, use_container_width=True):
                        append_tx(datetime.now().isoformat(timespec="seconds"), user, "check_out", k, 1, "")
                        # sync current_out for this tool
                        sync_current_out_in_tools()
                        st.experimental_rerun()

                with c2:
                    user_holds = user in holders
                    can_in = user_holds or is_admin
                    if st.button("Check In", key=f"in_{row['name']}_{row['category']}", disabled=not can_in, use_container_width=True):
                        # Only if something is out
                        if len(holders) > 0:
                            actor = user if user_holds else (user if is_admin else "Unknown")
                            append_tx(datetime.now().isoformat(timespec="seconds"), actor, "check_in", k, 1, "")
                            sync_current_out_in_tools()
                            st.experimental_rerun()

                with c3:
                    st.caption(f"Total Quantity: **{row['quantity']}**")

                # Admin edit/delete
                if is_admin:
                    with st.expander("Admin — Edit / Delete", expanded=False):
                        e1, e2, e3, e4 = st.columns([3,2,2,2])
                        with e1:
                            new_name = st.text_input("Rename", value=row["name"], key=f"rename_{row['name']}_{row['category']}")
                        with e2:
                            new_qty = st.number_input("Set quantity", min_value=0, value=int(row["quantity"]), step=1, key=f"setqty_{row['name']}_{row['category']}")
                        with e3:
                            if st.button("Update", key=f"upd_{row['name']}_{row['category']}", use_container_width=True):
                                tools2 = load_tools()
                                m = (tools2["name"]==row["name"]) & (tools2["category"]==row["category"])
                                tools2.loc[m, "name"] = new_name.strip() or row["name"]
                                tools2.loc[m, "quantity"] = int(new_qty)
                                df_to_ws(tools2, ws_tools)
                                sync_current_out_in_tools()
                                st.success("Updated.")
                                st.experimental_rerun()
                        with e4:
                            if st.button("Delete", key=f"del_{row['name']}_{row['category']}", use_container_width=True):
                                delete_tool(row["name"], row["category"])
                                st.success("Deleted.")
                                st.experimental_rerun()

                st.markdown('</div>', unsafe_allow_html=True)

    # Admin — Manage Employees
    if is_admin:
        with st.expander("Admin — Manage Employees", expanded=False):
            roster = load_roster().copy()
            st.write("**Current roster**")
            st.dataframe(roster, use_container_width=True, hide_index=True)
            st.write("**Add new employee**")
            r1, r2 = st.columns([3,1])
            with r1:
                new_emp = st.text_input("Full name", key="new_emp_name")
            with r2:
                if st.button("Add", key="add_emp_btn", use_container_width=True):
                    nm = (new_emp or "").strip()
                    if not nm:
                        st.warning("Enter a name.")
                    elif nm in roster["name"].values:
                        st.info("Already on roster.")
                    else:
                        roster.loc[len(roster)] = [nm, ""]
                        save_roster(roster)
                        st.success("Added.")
                        st.experimental_rerun()

            st.write("**Delete employee**")
            for idx, r in roster.reset_index(drop=True).iterrows():
                c1, c2 = st.columns([5,1])
                with c1:
                    st.text_input("Name", value=r["name"], key=f"ro_name_{idx}", disabled=True)
                with c2:
                    if st.button("Trash", key=f"ro_del_{idx}", use_container_width=True):
                        roster = roster[roster["name"] != r["name"]]
                        save_roster(roster)
                        st.success("Removed.")
                        st.experimental_rerun()

# Activity log viewer
with st.expander("Activity Log (latest 200)"):
    tx = load_tx()
    if tx.empty:
        st.info("No activity yet.")
    else:
        st.dataframe(tx.sort_values("ts", ascending=False).head(200), use_container_width=True)
