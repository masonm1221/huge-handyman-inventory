# app.py — HUGE Handyman Inventory (local CSV version)
# Features:
# - CSV storage in ./data (tools, roster, transactions, extra material logs)
# - Inline holder display next to "Unavailable"
# - Only the holder can check in (admins can always check in)
# - Categories (tools + text-entry categories)
# - Admin login (password from env ADMIN_PASSWORD or default)
# - Admin: add/update items, manage employee roster
# - Simple blue/orange theme. No logos.

import os
from pathlib import Path
from datetime import datetime
import uuid
import pandas as pd
import streamlit as st

# ======================== CONFIG / CONSTANTS =========================
APP_BRAND = "HUGE Handyman"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Huge2025")  # change in your .env if you want

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

TOOLS_CSV = DATA_DIR / "tools.csv"
ROSTER_CSV = DATA_DIR / "roster.csv"
TX_CSV = DATA_DIR / "transactions.csv"
EXTRA_MATERIAL_CSV = DATA_DIR / "extra_material_log.csv"
BAGS_ACC_CSV = DATA_DIR / "bags_accessories_log.csv"

TOOL_CATEGORIES = [
    "Power Tools",
    "Hand Tools",
    "Ladders",
    "Extension Cords",
    "Masking & Protection",
    "Batteries",
    "Blankets & Drop Cloths",
]

TEXT_CATEGORIES = [
    "Extra Material",
    "Bags / Accessories",
]

ALL_CATEGORIES = TOOL_CATEGORIES + TEXT_CATEGORIES

# ======================== PAGE SETUP / THEME =========================
st.set_page_config(page_title=f"{APP_BRAND} — Inventory", layout="wide")

HUGE_BLUE = "#0a4d8c"
HUGE_ORANGE = "#e75b2a"
HUGE_DARK = "#333333"
OK_GREEN = "#16a34a"
BAD_RED = "#dc2626"

st.markdown(
    f"""
<style>
  @font-face {{
    font-family: Inter;
    src: local("Inter"), local("system-ui");
  }}
  html, body, [class*="css"]  {{
    font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, Helvetica Neue, Arial, sans-serif;
  }}
  .hh-title {{
    font-weight: 900; font-size: 26px; letter-spacing: 0.2px; color:{HUGE_DARK};
  }}
  .chip {{
    display:inline-block; padding:4px 10px; border-radius: 999px; font-weight:700; font-size:12px; color:#fff;
  }}
  .chip.ok {{ background:{OK_GREEN}; }}
  .chip.bad {{ background:{BAD_RED}; }}
  .hh-small {{ color:#666; font-size:12px; }}
  .stButton > button {{
    border-radius: 10px; border:1px solid #e7e7e7;
  }}
  .blue-btn > button {{
    background:{HUGE_BLUE}; color:#fff; border:0;
  }}
  .orange-outline > button {{
    border:2px solid {HUGE_ORANGE}; color:{HUGE_ORANGE}; background:#fff;
  }}
  .stRadio > div > label {{
    padding:6px 10px; border-radius: 8px; border: 1px solid #e7e7e7; margin-right:8px;
  }}
  .tool-card {{
    border:1px solid #eee; border-radius:12px; padding:12px; margin-bottom:8px; background:#fff;
  }}
  .tool-name {{ font-weight: 700; font-size: 16px; }}
  .muted {{ color:#777; }}
</style>
""",
    unsafe_allow_html=True,
)

# ======================== STORAGE HELPERS ============================
def _ensure_csv(path: Path, columns: list[str]):
    if not path.exists():
        df = pd.DataFrame(columns=columns)
        df.to_csv(path, index=False)

def load_tools() -> pd.DataFrame:
    _ensure_csv(TOOLS_CSV, ["id", "name", "category", "quantity"])
    df = pd.read_csv(TOOLS_CSV)
    if "id" not in df.columns:
        df["id"] = ""
    if "quantity" in df.columns:
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0).astype(int)
    return df

def save_tools(df: pd.DataFrame):
    df.to_csv(TOOLS_CSV, index=False)

def load_roster() -> pd.DataFrame:
    _ensure_csv(ROSTER_CSV, ["name", "active"])
    df = pd.read_csv(ROSTER_CSV)
    if df.empty:
        df = pd.DataFrame([{"name":"Alex","active":1},{"name":"Brianna","active":1},{"name":"Chris","active":1}], columns=["name","active"])
        df.to_csv(ROSTER_CSV, index=False)
    return df

def save_roster(df: pd.DataFrame):
    df.to_csv(ROSTER_CSV, index=False)

def load_tx() -> pd.DataFrame:
    _ensure_csv(TX_CSV, ["ts", "tool_id", "tool_name", "user", "action"])
    return pd.read_csv(TX_CSV)

def append_tx(tool_id: str, tool_name: str, user: str, action: str):
    df = load_tx()
    df.loc[len(df)] = [
        datetime.now().isoformat(timespec="seconds"),
        str(tool_id),
        tool_name,
        user,
        action,
    ]
    df.to_csv(TX_CSV, index=False)

def current_holders(tool_id: str) -> list[str]:
    df = load_tx()
    if df.empty:
        return []
    sub = df[df["tool_id"] == str(tool_id)]
    if sub.empty:
        return []
    pivot = sub.pivot_table(index="user", columns="action", aggfunc="size", fill_value=0)
    outs = pivot["check_out"] if "check_out" in pivot.columns else 0
    ins  = pivot["check_in"]  if "check_in"  in pivot.columns else 0
    net = outs - ins
    holders = []
    if hasattr(net, "items"):
        for user, n in net.items():
            if n > 0:
                holders.extend([str(user)] * int(n))
    return holders

def available_count(quantity: int, holders: list[str]) -> int:
    return max(int(quantity) - len(holders), 0)

def load_text_log(which: str) -> Path:
    if which == "Extra Material":
        path = EXTRA_MATERIAL_CSV
    else:
        path = BAGS_ACC_CSV
    _ensure_csv(path, ["ts","user","entry"])
    return path

# ======================== SESSION DEFAULTS ===========================
if "is_admin" not in st.session_state:
    st.session_state["is_admin"] = False
if "current_user" not in st.session_state:
    st.session_state["current_user"] = ""

# ======================== SIDEBAR ===================================
with st.sidebar:
    st.markdown(f"<div class='hh-title'>{APP_BRAND}</div>", unsafe_allow_html=True)
    st.write("**Select your name**")

    roster_df = load_roster()
    active_names = ["—"] + sorted(roster_df[roster_df["active"]==1]["name"].astype(str).tolist())
    sel = st.selectbox("", active_names, index=0, key="roster_select")
    typed = st.text_input("Or type your name", key="typed_name")

    chosen = typed.strip() or ("" if sel=="—" else sel)
    st.session_state["current_user"] = chosen

    st.caption(f"Logged in as: **{st.session_state['current_user'] or 'Guest'}**")

    st.divider()
    st.write("**Admin Login**")
    pw = st.text_input("Password", type="password", key="admin_pw")
    col_a, col_b = st.columns([1,1])
    with col_a:
        if st.button("Login", use_container_width=True):
            if pw == ADMIN_PASSWORD:
                st.session_state["is_admin"] = True
                st.success("Admin mode enabled")
                st.rerun()
            else:
                st.error("Wrong password")
    with col_b:
        if st.button("Logout", use_container_width=True):
            st.session_state["is_admin"] = False
            st.rerun()

# ======================== HEADER + CATEGORY PICKER ===================
st.markdown(f"<div class='hh-title'>Tool Inventory</div>", unsafe_allow_html=True)

cat = st.radio("Select Category:", ALL_CATEGORIES, horizontal=True, index=0)

# ======================== TEXT CATEGORIES ============================
if cat in TEXT_CATEGORIES:
    st.subheader(cat)

    log_path = load_text_log(cat)

    with st.form(f"form_{cat.replace(' ','_')}"):
        entry = st.text_input("Describe what you’re taking", placeholder="e.g., 1 Milwaukee bag with 2 fine tool blades")
        submitted = st.form_submit_button("Submit")
        if submitted:
            if not st.session_state["current_user"]:
                st.warning("Pick your name (left sidebar) first.")
            elif not entry.strip():
                st.warning("Please type something to record.")
            else:
                df = pd.read_csv(log_path)
                df.loc[len(df)] = [
                    datetime.now().isoformat(timespec="seconds"),
                    st.session_state["current_user"],
                    entry.strip()
                ]
                df.to_csv(log_path, index=False)
                st.success("Logged.")
                st.rerun()

    # recent entries
    df_log = pd.read_csv(log_path)
    if df_log.empty:
        st.info("No entries yet.")
    else:
        st.dataframe(df_log.sort_values("ts", ascending=False).head(100), use_container_width=True)

# ======================== TOOL CATEGORIES ===========================
else:
    # Admin add/update form
    is_admin = bool(st.session_state["is_admin"])
    tools_df = load_tools()

    st.subheader(cat)

    if is_admin:
        st.markdown("**Admin — Add or Update**")
        col1, col2, col3 = st.columns([5,2,2])
        with col1:
            new_name = st.text_input("Item name", key="new_tool_name")
        with col2:
            new_qty = st.number_input("Quantity", min_value=0, step=1, value=0, key="new_tool_qty")
        with col3:
            st.write("")
            if st.button("Save to selected category", key="save_tool_btn", use_container_width=True):
                name = (new_name or "").strip()
                if not name:
                    st.warning("Enter a name.")
                else:
                    # if exists in this category, update; else insert
                    mask = (tools_df["name"].astype(str).str.lower()==name.lower()) & (tools_df["category"]==cat)
                    if mask.any():
                        tools_df.loc[mask, "quantity"] = int(new_qty)
                    else:
                        tools_df.loc[len(tools_df)] = [str(uuid.uuid4()), name, cat, int(new_qty)]
                    save_tools(tools_df)
                    st.success("Saved.")
                    st.rerun()

    # show items for category
    view_df = tools_df[tools_df["category"]==cat].copy()
    if view_df.empty:
        st.info("No items found for this category.")
    else:
        # Sort by name
        view_df = view_df.sort_values("name", key=lambda s: s.str.lower())
        for _, row in view_df.iterrows():
            with st.container(border=True):
                # Name + status line
                st.markdown(f"<div class='tool-name'>{row['name']}</div>", unsafe_allow_html=True)
                holders = current_holders(str(row["id"]))
                avail = available_count(int(row["quantity"]), holders)

                # status line with holders shown next to Unavailable
                if avail > 0:
                    st.markdown(f"<span class='chip ok'>Available</span> &nbsp; <span class='muted'>({avail} available of {row['quantity']})</span>", unsafe_allow_html=True)
                else:
                    holder_names = ", ".join(sorted(set(holders))) if holders else "—"
                    st.markdown(
                        f"<span class='chip bad'>Unavailable</span> &nbsp; "
                        f"<span class='hh-small'>Holder:</span> {holder_names} "
                        f"<span class='muted'>(total {row['quantity']})</span>",
                        unsafe_allow_html=True
                    )

                # actions
                colA, colB, colC = st.columns([1,1,2])
                current_user = st.session_state.get("current_user", "").strip() or "Guest"

                with colA:
                    can_checkout = (avail > 0) and (current_user != "" and current_user.lower() != "guest")
                    if st.button("Check Out", key=f"out_{row['id']}", disabled=not can_checkout, use_container_width=True):
                        append_tx(str(row["id"]), row["name"], current_user, "check_out")
                        st.rerun()

                with colB:
                    # Only current holder OR admin can check in
                    user_holds_this = current_user in holders
                    can_checkin = user_holds_this or is_admin
                    if st.button("Check In", key=f"in_{row['id']}", disabled=not can_checkin, use_container_width=True):
                        if len(holders) > 0:
                            actor = current_user if user_holds_this else (current_user if is_admin else "Unknown")
                            append_tx(str(row["id"]), row["name"], actor, "check_in")
                            st.rerun()

                with colC:
                    st.caption(f"Total Quantity: **{row['quantity']}**")

                # Admin delete/edit controls
                if is_admin:
                    with st.expander("Admin — Edit / Delete", expanded=False):
                        ec1, ec2, ec3 = st.columns([3,2,2])
                        with ec1:
                            new_n = st.text_input("Rename", value=row["name"], key=f"rename_{row['id']}")
                        with ec2:
                            new_q = st.number_input("Set quantity", min_value=0, value=int(row["quantity"]), step=1, key=f"setqty_{row['id']}")
                        with ec3:
                            upd = st.button("Update", key=f"upd_{row['id']}", use_container_width=True)
                        delcol = st.columns([1,1])[1]
                        with delcol:
                            rem = st.button("Delete", key=f"del_{row['id']}", use_container_width=True)
                        if upd:
                            tools_df.loc[tools_df["id"]==row["id"], "name"] = new_n.strip() or row["name"]
                            tools_df.loc[tools_df["id"]==row["id"], "quantity"] = int(new_q)
                            save_tools(tools_df)
                            st.success("Updated.")
                            st.rerun()
                        if rem:
                            tools_df = tools_df[tools_df["id"]!=row["id"]]
                            save_tools(tools_df)
                            st.success("Deleted.")
                            st.rerun()

    # ===================== Admin — Manage Employees ==================
    if is_admin:
        with st.expander("Admin — Manage Employees", expanded=False):
            roster = load_roster().copy()
            st.write("**Current roster**")
            st.dataframe(roster, use_container_width=True, hide_index=True)

            st.write("**Add new employee**")
            nc1, nc2 = st.columns([3,1])
            with nc1:
                new_emp = st.text_input("Full name", key="new_emp_name")
            with nc2:
                if st.button("Add", key="add_emp_btn", use_container_width=True):
                    name = (new_emp or "").strip()
                    if not name:
                        st.warning("Enter a name.")
                    elif name in roster["name"].values:
                        st.info("Already on roster.")
                    else:
                        roster.loc[len(roster)] = [name, 1]
                        save_roster(roster)
                        st.success("Added.")
                        st.rerun()

            st.write("**Toggle active / Delete**")
            # Simple toggles
            for idx, r in roster.iterrows():
                c1, c2, c3 = st.columns([4,2,2])
                with c1:
                    st.text_input("Name", value=r["name"], key=f"ro_name_{idx}", disabled=True)
                with c2:
                    active_now = st.checkbox("Active", value=bool(r["active"]), key=f"ro_act_{idx}")
                with c3:
                    if st.button("Delete", key=f"ro_del_{idx}", use_container_width=True):
                        roster = roster[roster["name"] != r["name"]]
                        save_roster(roster)
                        st.success("Removed.")
                        st.rerun()
                # persist active toggle
                roster.loc[roster["name"]==r["name"], "active"] = 1 if st.session_state.get(f"ro_act_{idx}", bool(r["active"])) else 0
            save_roster(roster)

# ===================== Activity Log (optional) =======================
with st.expander("Activity Log (latest 200)"):
    tx = load_tx()
    if tx.empty:
        st.info("No activity yet.")
    else:
        st.dataframe(tx.sort_values("ts", ascending=False).head(200), use_container_width=True)
