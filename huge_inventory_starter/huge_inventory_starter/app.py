# Author: HUGE Handyman + ChatGPT
# Streamlit + PostgreSQL (SQLAlchemy)
# Inventory app with photos, "Your current tools", admin edit/delete, and activity log

import os
from datetime import datetime
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

# -----------------------------------------------------------------------------
# Config & Styling
# -----------------------------------------------------------------------------
APP_BRAND = "HUGE Handyman"
HUGE_BLUE = "#004B8D"
HUGE_ORANGE = "#E75B2A"
HUGE_DARK = "#333333"

st.set_page_config(page_title=f"{APP_BRAND} Inventory", layout="wide")

st.markdown(
    f"""
    <style>
      .hh-header {{
        width: 100%; padding: 12px 18px; background: white; border-bottom: 2px solid #eee;
        display: flex; align-items: center; justify-content: space-between; position: sticky;
        top: 0; z-index: 100; box-shadow: 0 2px 10px rgba(0,0,0,0.04);
      }}
      .hh-left {{display:flex;align-items:center;gap:16px;}}
      .hh-title {{font-weight: 800; font-size: 22px; color: {HUGE_DARK}; letter-spacing: .5px;}}

      .chip {{ display:inline-block; padding:4px 10px; border-radius:999px; font-weight:700; font-size:12px; color:white; }}
      .chip.ok {{ background:#16a34a; }}
      .chip.bad {{ background:#dc2626; }}
      .chip.warn {{ background:#f59e0b; color:#111; }}

      .stButton>button {{ border-radius:10px; border:2px solid {HUGE_BLUE}; color:{HUGE_BLUE}; }}
      .stButton>button:hover {{ filter: brightness(1.05); }}
      div.stButton>button[kind="secondary"] {{ border:2px solid {HUGE_ORANGE}; color:{HUGE_ORANGE}; }}
      div.stButton>button[kind="primary"] {{ background:{HUGE_BLUE}; color:white; border:2px solid {HUGE_BLUE}; }}

      /* Orange category bar */
      .catbar {{ display:flex; flex-wrap:wrap; gap:10px; margin: 8px 0 18px; }}
      .catbar .stButton > button {{
          background: {HUGE_ORANGE};
          color: #fff;
          border: 2px solid {HUGE_ORANGE};
          border-radius: 10px;
          padding: 8px 14px;
          font-weight: 700;
      }}
      .catbar .stButton > button:hover {{ filter: brightness(1.08); }}
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# Database (Render Postgres or local SQLite fallback)
# -----------------------------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///local.db")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def init_db():
    # Base schema (includes image_url for fresh installs)
    schema_sql = """
    create table if not exists tools (
        id serial primary key,
        name text unique,
        category text,
        quantity int default 0,
        current_out int default 0,
        image_url text
    );

    create table if not exists users (
        id serial primary key,
        name text unique,
        pin text
    );

    create table if not exists transactions (
        id serial primary key,
        tool_id int,
        user_name text,
        action text check (action in ('check_out','check_in')),
        ts timestamptz default now()
    );

    create table if not exists extra_material_log (
        id serial primary key,
        user_name text,
        entry text,
        ts timestamptz default now()
    );

    create table if not exists bags_accessories_log (
        id serial primary key,
        user_name text,
        entry text,
        ts timestamptz default now()
    );
    """
    with engine.begin() as conn:
        # Create tables (no data loss)
        for stmt in schema_sql.strip().split(";\n\n"):
            if stmt.strip():
                conn.execute(text(stmt + ";"))

        # Add image_url if table pre-existed without it (safe attempts)
        try:
            conn.execute(text("alter table tools add column if not exists image_url text;"))
        except Exception:
            try:
                conn.execute(text("alter table tools add column image_url text;"))
            except Exception:
                pass

init_db()

def db_read_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)

def db_exec(sql: str, params: dict | None = None):
    with engine.begin() as conn:
        conn.execute(text(sql), params or {})

# -----------------------------------------------------------------------------
# Data helpers
# -----------------------------------------------------------------------------
CATEGORIES = [
    "Power Tools",
    "Hand Tools",
    "Ladders",
    "Extension Cords",
    "Masking & Protection",
    "Batteries",
    "Blankets & Drop Cloths",
    "Extra Material",
    "Bags / Accessories",
    "Vacuums / Fans",
    "Uncommon Tools",
]

TEXT_LOGS = {
    "Extra Material": "extra_material_log",
    "Bags / Accessories": "bags_accessories_log",
}

def upsert_tool(name: str, category: str, quantity: int, image_url: str | None = None):
    db_exec(
        """
        insert into tools(name, category, quantity, image_url)
        values (:n, :c, :q, :img)
        on conflict(name)
        do update set category = excluded.category,
                      quantity = excluded.quantity,
                      image_url = excluded.image_url
        """,
        {"n": name.strip(), "c": category, "q": int(quantity), "img": (image_url or "").strip()},
    )

def update_tool_fields(tool_id: int, name: str, category: str, quantity: int, image_url: str | None = None):
    db_exec(
        """
        update tools
           set name = :n,
               category = :c,
               quantity = :q,
               image_url = :img
         where id = :tid
        """,
        {"n": name.strip(), "c": category, "q": int(quantity), "img": (image_url or "").strip(), "tid": tool_id},
    )

def delete_tool(tool_id: int, delete_history: bool = False):
    if delete_history:
        db_exec("delete from transactions where tool_id = :tid", {"tid": tool_id})
    db_exec("delete from tools where id = :tid", {"tid": tool_id})

def list_tools_by_category(cat: str) -> pd.DataFrame:
    df = db_read_df("select * from tools where category = :c order by name", {"c": cat})
    if not df.empty:
        df["available_qty"] = (df["quantity"].fillna(0).astype(int) - df["current_out"].fillna(0).astype(int)).clip(lower=0)
    return df

def record_checkout(tool_id: int, user_name: str) -> bool:
    df = db_read_df("select quantity, current_out from tools where id = :tid", {"tid": tool_id})
    if df.empty:
        return False
    available = int(df.iloc[0]["quantity"]) - int(df.iloc[0]["current_out"])
    if available <= 0:
        return False
    db_exec("update tools set current_out = current_out + 1 where id = :tid", {"tid": tool_id})
    db_exec(
        "insert into transactions(tool_id, user_name, action) values (:tid, :u, 'check_out')",
        {"tid": tool_id, "u": user_name},
    )
    return True

def record_checkin(tool_id: int, user_name: str) -> bool:
    db_exec("update tools set current_out = greatest(current_out - 1, 0) where id = :tid", {"tid": tool_id})
    db_exec(
        "insert into transactions(tool_id, user_name, action) values (:tid, :u, 'check_in')",
        {"tid": tool_id, "u": user_name},
    )
    return True

def last_holder(tool_id: int) -> str | None:
    df = db_read_df(
        """
        select user_name, action
          from transactions
         where tool_id = :tid
         order by ts desc
         limit 1
        """,
        {"tid": tool_id},
    )
    if not df.empty and df.iloc[0]["action"] == "check_out":
        return df.iloc[0]["user_name"]
    return None

def log_text(which: str, user_name: str, entry: str):
    table = "extra_material_log" if which == "extra" else "bags_accessories_log"
    db_exec(
        f"insert into {table}(user_name, entry) values (:u, :e)",
        {"u": user_name, "e": entry.strip()},
    )

def read_log(table: str, limit: int = 50) -> pd.DataFrame:
    return db_read_df(f"select user_name, entry, ts from {table} order by ts desc limit {limit}")

def read_transactions(limit: int = 100) -> pd.DataFrame:
    sql = """
        select t.ts,
               t.user_name,
               case t.action when 'check_out' then 'Checked Out' when 'check_in' then 'Checked In' end as action,
               coalesce(z.name, concat('Tool #', t.tool_id::text)) as tool_name
          from transactions t
     left join tools z
            on z.id = t.tool_id
         order by t.ts desc
         limit :lim;
    """
    return db_read_df(sql, {"lim": limit})

def user_current_tools(user_name: str) -> pd.DataFrame:
    # Net outstanding per tool for this user: (check_out - check_in) > 0
    sql = """
    select
        t.id,
        t.name,
        t.category,
        t.quantity,
        t.current_out,
        t.image_url,
        coalesce(sum(case when tr.action='check_out' then 1
                          when tr.action='check_in'  then -1
                     else 0 end),0) as mine_out
    from tools t
    left join transactions tr
      on tr.tool_id = t.id and tr.user_name = :u
    group by t.id, t.name, t.category, t.quantity, t.current_out, t.image_url
    having coalesce(sum(case when tr.action='check_out' then 1
                             when tr.action='check_in'  then -1
                        else 0 end),0) > 0
    order by t.category, t.name
    """
    return db_read_df(sql, {"u": user_name})

# Roster
def list_users() -> list[str]:
    df = db_read_df("select name from users order by name")
    return df["name"].tolist() if not df.empty else []

def add_user(name: str, pin: str | None = None):
    db_exec(
        "insert into users(name, pin) values (:n, :p) on conflict(name) do nothing",
        {"n": name.strip(), "p": (pin or "").strip()},
    )

def delete_user(name: str):
    db_exec("delete from users where name = :n", {"n": name})

# -----------------------------------------------------------------------------
# Session & Auth
# -----------------------------------------------------------------------------
if "is_admin" not in st.session_state:
    st.session_state["is_admin"] = False
if "current_user" not in st.session_state:
    st.session_state["current_user"] = "Guest"
if "active_cat" not in st.session_state:
    st.session_state["active_cat"] = CATEGORIES[0]

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")

# -----------------------------------------------------------------------------
# Header & Sidebar
# -----------------------------------------------------------------------------
st.markdown('<div class="hh-header">', unsafe_allow_html=True)
st.markdown(f'<div class="hh-left"><div class="hh-title">{APP_BRAND} — Inventory</div></div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# Sidebar: choose user
st.sidebar.header(APP_BRAND)
roster = list_users()
picked = st.sidebar.selectbox("Select your name", ["—"] + roster, index=0)
typed_name = st.sidebar.text_input("Or type your name")

if st.sidebar.button("Use Roster"):
    if picked and picked != "—":
        st.session_state["current_user"] = picked
    elif typed_name.strip():
        st.session_state["current_user"] = typed_name.strip()

# Admin login
st.sidebar.subheader("Admin Login")
admin_pw = st.sidebar.text_input("Password", type="password")
if st.sidebar.button("Login"):
    st.session_state["is_admin"] = (admin_pw == ADMIN_PASSWORD)
if st.session_state["is_admin"]:
    st.sidebar.success("Admin mode enabled")
    if st.sidebar.button("Logout"):
        st.session_state["is_admin"] = False

# Roster management (admin)
with st.sidebar.expander("Admin — Manage Employees", expanded=False):
    st.caption("Add / remove names for the employee dropdown.")
    new_emp = st.text_input("Add employee name", key="add_emp_name")
    new_pin = st.text_input("Optional PIN", key="add_emp_pin")
    cols = st.columns([1,1,1])
    if cols[0].button("Add to roster"):
        if new_emp.strip():
            add_user(new_emp.strip(), new_pin.strip())
            st.success(f"Added {new_emp}")
            st.rerun()
    if roster:
        rm_emp = st.selectbox("Delete employee", ["—"] + roster, key="rm_emp")
        if cols[1].button("Delete selected") and rm_emp != "—":
            delete_user(rm_emp)
            st.warning(f"Deleted {rm_emp}")
            st.rerun()

# -----------------------------------------------------------------------------
# Logged-in user line
# -----------------------------------------------------------------------------
user = st.session_state.get("current_user", "Guest")
st.caption(f"Logged in as: **{user}**")

# -----------------------------------------------------------------------------
# Your current tools (for the logged-in user)
# -----------------------------------------------------------------------------
if user and user != "Guest":
    my_df = user_current_tools(user)
    if not my_df.empty:
        st.markdown("### Your current tools")
        for _, r in my_df.iterrows():
            tool_id = int(r["id"])
            name = r["name"]
            mine_out = int(r["mine_out"])
            qty = int(r.get("quantity", 0) or 0)
            current_out = int(r.get("current_out", 0) or 0)
            img = (r.get("image_url") or "").strip()

            with st.container(border=True):
                c1, c2, c3 = st.columns([4,2,3])
                with c1:
                    if img:
                        st.image(img, width=90)
                    st.markdown(f"**{name}**")
                    st.caption(f"You have: {mine_out}  |  Out (all users): {current_out}  |  Total: {qty}")

                with c2:
                    st.markdown("<span class='chip bad'>Checked Out</span>", unsafe_allow_html=True)

                with c3:
                    b1, b2 = st.columns(2)
                    if b1.button("Return 1", key=f"mine_return1_{tool_id}"):
                        record_checkin(tool_id, user)
                        st.rerun()
                    if mine_out > 1:
                        if b2.button(f"Return all ({mine_out})", key=f"mine_returnall_{tool_id}"):
                            for _ in range(mine_out):
                                record_checkin(tool_id, user)
                            st.rerun()

# -----------------------------------------------------------------------------
# Category bar (single, orange)
# -----------------------------------------------------------------------------
st.markdown('<div class="catbar">', unsafe_allow_html=True)
cols = st.columns(len(CATEGORIES), gap="small")
for i, label in enumerate(CATEGORIES):
    with cols[i]:
        if st.button(label, key=f"catbtn_{i}"):
            st.session_state["active_cat"] = label
            st.rerun()   # Immediate UI update (prevents double-click)
st.markdown("</div>", unsafe_allow_html=True)

active_cat = st.session_state["active_cat"]
st.subheader(active_cat)

# -----------------------------------------------------------------------------
# Content for the selected category
# -----------------------------------------------------------------------------
if active_cat in TEXT_LOGS:
    # Text-entry categories
    table = TEXT_LOGS[active_cat]
    with st.form(f"log_form_{table}"):
        entry = st.text_input("Describe what you’re taking:", placeholder="e.g., 1 Milwaukee bag with 2 fine tool blades")
        submitted = st.form_submit_button("Submit")
        if submitted and entry.strip():
            log_text("extra" if table == "extra_material_log" else "bags", user, entry)
            st.success("Logged successfully!")
            st.rerun()

    logs = read_log(table, limit=50)
    if logs.empty:
        st.info("No entries yet.")
    else:
        st.dataframe(logs, use_container_width=True)

else:
    # Tools category
    # Admin add/update
    if st.session_state["is_admin"]:
        st.markdown("**Admin — Add or Update**")
        with st.form("admin_add_update"):
            new_tool = st.text_input("Item name")
            new_qty = st.number_input("Quantity", min_value=0, value=0, step=1)
            new_img = st.text_input("Image URL (optional)", placeholder="https://…/tool.jpg or .png")
            saved = st.form_submit_button("Save to selected category")
            if saved and new_tool.strip():
                upsert_tool(new_tool.strip(), active_cat, int(new_qty), new_img.strip())
                st.success(f"Saved '{new_tool}' to {active_cat}")
                st.rerun()

    q = st.text_input("Search items…", placeholder="Type to filter by name")
    df = list_tools_by_category(active_cat)
    if not df.empty and q:
        df = df[df["name"].str.contains(q, case=False, na=False)]

    if df.empty:
        st.info("No items found for this category.")
    else:
        for _, row in df.iterrows():
            tool_id = int(row["id"])
            name = row["name"]
            qty = int(row.get("quantity", 0) or 0)
            current_out = int(row.get("current_out", 0) or 0)
            available_qty = qty - current_out
            holder = last_holder(tool_id)
            img = (row.get("image_url") or "").strip()

            status_html = ""
            if available_qty > 0:
                status_html = f"<span class='chip ok'>Available</span> ({available_qty})"
            else:
                if holder:
                    status_html = f"<span class='chip bad'>Unavailable</span> — held by **{holder}**"
                else:
                    status_html = f"<span class='chip bad'>Unavailable</span>"

            with st.container(border=True):
                c1, c2, c3 = st.columns([4,2,3])
                with c1:
                    if img:
                        st.image(img, width=90)
                    st.markdown(f"**{name}**")
                    st.caption(f"Total: {qty}  |  Out: {current_out}")
                with c2:
                    st.markdown(status_html, unsafe_allow_html=True)
                with c3:
                    is_admin = st.session_state["is_admin"]

                    colb1, colb2 = st.columns(2)

                    # CHECK OUT
                    if available_qty > 0:
                        if colb1.button("Check Out", key=f"out_{tool_id}_{name}"):
                            ok = record_checkout(tool_id, user)
                            if not ok:
                                st.warning("No available quantity.")
                            st.rerun()
                    else:
                        colb1.button("Check Out", key=f"out_{tool_id}_{name}", disabled=True)

                    # CHECK IN (only holder or admin)
                    can_checkin = (current_out > 0) and (is_admin or (holder == user))
                    if colb2.button("Check In", key=f"in_{tool_id}_{name}", disabled=not can_checkin):
                        if can_checkin:
                            record_checkin(tool_id, user)
                            st.rerun()
                        else:
                            st.error("Only the current holder or admin can check this in.")

                # ---------- Admin: Edit / Delete ----------
                if st.session_state["is_admin"]:
                    with st.expander("Admin: edit / delete", expanded=False):
                        new_name = st.text_input("Name", value=name, key=f"nm_{tool_id}")
                        new_qty = st.number_input("Quantity", value=qty, min_value=0, step=1, key=f"qt_{tool_id}")
                        new_cat = st.selectbox(
                            "Category",
                            CATEGORIES,
                            index=CATEGORIES.index(active_cat) if active_cat in CATEGORIES else 0,
                            key=f"ct_{tool_id}",
                        )
                        new_img2 = st.text_input("Image URL", value=img, key=f"img_{tool_id}")
                        cols_admin = st.columns([1,1,1])
                        if cols_admin[0].button("Save changes", key=f"save_{tool_id}"):
                            try:
                                update_tool_fields(tool_id, new_name, new_cat, int(new_qty), new_img2.strip())
                                st.success("Updated.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Could not update: {e}")

                        delete_history = st.checkbox("Also delete history", value=False, key=f"dh_{tool_id}")
                        if cols_admin[2].button("Delete tool", key=f"del_{tool_id}"):
                            try:
                                delete_tool(tool_id, delete_history=delete_history)
                                st.warning("Tool deleted.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Could not delete: {e}")

# -----------------------------------------------------------------------------
# Admin Activity Log (read-only)
# -----------------------------------------------------------------------------
if st.session_state["is_admin"]:
    with st.expander("Admin — Activity Log (last 100)", expanded=False):
        tx = read_transactions(limit=100)
        if tx.empty:
            st.info("No transactions yet.")
        else:
            tx = tx.rename(columns={"ts": "Timestamp", "user_name": "User", "action": "Action", "tool_name": "Tool"})
            st.dataframe(tx, use_container_width=True)

# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------
st.divider()
st.caption("© HUGE Handyman — simple inventory (PostgreSQL)")
