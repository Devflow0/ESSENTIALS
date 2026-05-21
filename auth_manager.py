import streamlit as st
import sqlite3
import hashlib
import pandas as pd
import base64
import os
import json
import ui_utils

DB_NAME = 'alpr_data.db'

# All pages available in the app (admin always gets all)
ALL_PAGES = [
    "Security Dashboard",
    "Face Recognition",
    "Airport Reminders",
    "Expenses",
    "Vehicle Tracker",
    "Maintenance",
    "Logbook",
]

# --- UTILS ---
def hash_password(password):
    """Encodes the password using SHA-256 for security."""
    return hashlib.sha256(str.encode(password)).hexdigest()

def init_user_db():
    """Initializes the user table and creates the master admin."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                          (username TEXT PRIMARY KEY, password TEXT, role TEXT,
                           user_pages TEXT DEFAULT NULL)''')

        # Migrate existing DB: add user_pages column if missing
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN user_pages TEXT DEFAULT NULL")
        except sqlite3.OperationalError:
            pass  # column already exists

        # Check if the default admin exists
        cursor.execute("SELECT * FROM users WHERE username = 'ADMINISTRATOR'")
        if not cursor.fetchone():
            admin_pw = hash_password("BWG_ADMIN")
            cursor.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?)",
                ("ADMINISTRATOR", admin_pw, "admin", json.dumps(ALL_PAGES))
            )
        conn.commit()

def _get_login_image_b64():
    """Load the login background image as a base64 string."""
    img_path = os.path.join(os.path.dirname(__file__), "assets", "images", "backgrounds", "login_bg.png")
    if os.path.exists(img_path):
        with open(img_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None

# --- CORE LOGIC ---
def check_login(username, password):
    """Verifies credentials and returns the user's role if successful."""
    hashed_pw = hash_password(password)
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE username = ? AND password = ?", (username, hashed_pw))
        result = cursor.fetchone()
        return result[0] if result else None

def create_user(new_user, new_pw, is_admin=False, pages=None):
    """Adds a new user to the database. is_admin=True grants admin privileges."""
    try:
        hashed_pw = hash_password(new_pw)
        role = "admin" if is_admin else "user"
        pages_json = json.dumps(pages if pages is not None else [])
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?)",
                (new_user, hashed_pw, role, pages_json)
            )
            conn.commit()
        return True
    except:
        return False

def get_user_pages(username):
    """Returns the list of pages assigned to a user (admin gets all pages)."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT role, user_pages FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
    if not row:
        return []
    role, pages_json = row
    if role == "admin":
        return ALL_PAGES + ["Admin Settings"]
    if pages_json:
        try:
            return json.loads(pages_json)
        except (json.JSONDecodeError, TypeError):
            pass
    return []

def set_user_pages(username, pages):
    """Updates the page list for a given user."""
    pages_json = json.dumps(pages)
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("UPDATE users SET user_pages = ? WHERE username = ?", (pages_json, username))
        conn.commit()

def delete_user(username):
    """Removes a user from the system."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()

def update_password(username, new_pw):
    """Updates the password for the currently logged-in user."""
    hashed_pw = hash_password(new_pw)
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("UPDATE users SET password = ? WHERE username = ?", (hashed_pw, username))
        conn.commit()

def set_admin(username, is_admin: bool):
    """Sets or removes admin privileges for a user."""
    role = "admin" if is_admin else "user"
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("UPDATE users SET role = ? WHERE username = ?", (role, username))
        conn.commit()

# --- UI COMPONENTS ---
def login_page():
    """Renders the login screen with a split-screen layout. Returns True if authenticated."""
    init_user_db()

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:

        # ── Load the hero image ───────────────────────────────────────────
        img_b64 = _get_login_image_b64()
        img_bg = ""
        if img_b64:
            img_bg = f"background-image: url('data:image/jpeg;base64,{img_b64}');"

        # ── Inject all CSS + the background HTML in one block ─────────────
        st.markdown(f"""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

            /* ── Reset Streamlit chrome on login ──────────────────────── */
            [data-testid="stSidebar"]          {{ display: none !important; }}
            [data-testid="stHeader"]           {{ display: none !important; }}
            footer                              {{ display: none !important; }}
            [data-testid="stMainBlockContainer"] {{
                padding: 0 !important; max-width: 100% !important;
            }}
            [data-testid="stMain"]              {{ padding: 0 !important; }}
            .block-container {{
                padding: 0 !important; max-width: 100% !important;
            }}

            /* ── Split-screen wrapper ─────────────────────────────────── */
            .login-split {{
                display: flex;
                min-height: 100vh;
                width: 100vw;
                position: fixed;
                top: 0; left: 0;
                z-index: 999;
                font-family: 'Inter', 'Segoe UI', sans-serif;
            }}

            /* Left: image panel */
            .login-img {{
                flex: 1 1 50%;
                {img_bg}
                background-size: cover;
                background-position: center;
                position: relative;
            }}
            .login-img::after {{
                content: '';
                position: absolute;
                inset: 0;
                background: linear-gradient(135deg,
                    rgba(21,101,192,0.18) 0%,
                    rgba(0,0,0,0.08) 100%);
            }}

            /* Right: form panel — everything vertically centered */
            .login-panel {{
                flex: 1 1 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                background: #ffffff;
                padding: 2rem 3rem;
                overflow-y: auto;
            }}
            .login-card {{
                width: 100%;
                max-width: 420px;
            }}

            /* Heading block */
            .login-card .lc-heading {{
                font-size: 1.85rem;
                font-weight: 700;
                color: #1a1a2e;
                margin: 0 0 0.35rem 0;
                letter-spacing: -0.5px;
            }}
            .login-card .lc-sub {{
                font-size: 0.92rem;
                color: #6b7280;
                line-height: 1.55;
                margin-bottom: 1.8rem;
            }}

            /* ── Responsive: stack on small screens ───────────────────── */
            @media (max-width: 860px) {{
                .login-split {{ flex-direction: column; }}
                .login-img  {{ flex: 0 0 35vh; min-height: 200px; }}
                .login-panel {{ flex: 1 1 auto; padding: 1.5rem; }}
            }}
            @media (max-width: 480px) {{
                .login-img   {{ flex: 0 0 25vh; }}
                .login-panel {{ padding: 1rem; }}
                .login-card .lc-heading {{ font-size: 1.4rem; }}
                .login-card .lc-sub    {{ font-size: 0.82rem; }}
            }}
        </style>

        <!-- Background split (image left, blank white right) -->
        <div class="login-split">
            <div class="login-img"></div>
            <div class="login-panel"></div>
        </div>
        """, unsafe_allow_html=True)

        # ── CSS to position the Streamlit form inside the right panel ─────
        st.markdown("""
        <style>
            /* Overlay the real Streamlit form below the welcome heading */
            [data-testid="stForm"] {
                position: fixed !important;
                top: 0;
                right: 0;
                width: 50vw;
                max-width: 50vw;
                height: 100vh;
                z-index: 1001;
                background: transparent !important;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 0 3rem;
                box-sizing: border-box;
            }
            [data-testid="stForm"] > div:first-child {
                border: none !important;
                padding: 0 !important;
                background: transparent !important;
                max-width: 420px;
                width: 100%;
            }

            /* Input styling — explicit color so password dots are visible */
            [data-testid="stForm"] .stTextInput > div > div > input,
            [data-testid="stForm"] .stTextInput > div > div > input[type="password"] {
                border: 1px solid #e0e0e0 !important;
                border-radius: 6px !important;
                padding: 0.65rem 0.9rem !important;
                font-size: 0.92rem !important;
                font-family: 'Inter', sans-serif !important;
                background: #fff !important;
                color: #1a1a2e !important;
                -webkit-text-fill-color: #1a1a2e !important;
                -webkit-text-security: disc;
                caret-color: #1a1a2e !important;
                transition: border-color 0.2s ease;
            }
            /* Ensure regular text inputs show normal text, not dots */
            [data-testid="stForm"] .stTextInput > div > div > input[type="text"] {
                -webkit-text-security: none;
            }
            [data-testid="stForm"] .stTextInput > div > div > input:focus {
                border-color: #c8d830 !important;
                box-shadow: 0 0 0 2px rgba(200,216,48,0.25) !important;
            }
            [data-testid="stForm"] .stTextInput label {
                font-size: 0.82rem !important;
                font-weight: 500 !important;
                color: #4b5563 !important;
                font-family: 'Inter', sans-serif !important;
            }

            /* Submit button — yellow-green like the reference */
            [data-testid="stForm"] button[kind="formSubmit"] {
                background: linear-gradient(135deg, #c8d830, #a8b820) !important;
                color: #1a1a2e !important;
                border: none !important;
                border-radius: 6px !important;
                padding: 0.6rem 2.2rem !important;
                font-weight: 600 !important;
                font-size: 0.92rem !important;
                font-family: 'Inter', sans-serif !important;
                cursor: pointer;
                transition: all 0.25s ease;
                width: auto !important;
            }
            [data-testid="stForm"] button[kind="formSubmit"]:hover {
                background: linear-gradient(135deg, #d4e43c, #b8c82c) !important;
                box-shadow: 0 4px 14px rgba(200,216,48,0.40) !important;
                transform: translateY(-1px);
            }

            /* Checkbox */
            [data-testid="stForm"] .stCheckbox label {
                font-family: 'Inter', sans-serif !important;
                font-size: 0.85rem !important;
                color: #6b7280 !important;
            }

            /* ── Responsive: reposition form on small screens ─────── */
            @media (max-width: 860px) {
                [data-testid="stForm"] {
                    width: 100vw !important;
                    max-width: 100vw !important;
                    right: 0 !important;
                    top: auto !important;
                    bottom: 0 !important;
                    transform: none !important;
                    padding: 1.5rem !important;
                    background: #fff !important;
                }
            }
            @media (max-width: 480px) {
                [data-testid="stForm"] {
                    padding: 1rem !important;
                }
            }
        </style>
        """, unsafe_allow_html=True)

        # ── Streamlit form widgets ────────────────────────────────────────
        with st.form("login_form"):
            # Welcome heading — inside the form so it flows above the fields
            st.markdown("""
            <h1 style="font-family:'Inter',sans-serif; font-size:1.85rem; font-weight:700;
                        color:#1a1a2e; margin:0 0 0.3rem 0; letter-spacing:-0.5px;">
                Welcome Back
            </h1>
            <p style="font-family:'Inter',sans-serif; font-size:0.92rem; color:#6b7280;
                       line-height:1.55; margin-bottom:1.5rem;">
                Sign in to manage properties, track performance,<br>
                and keep your operations running smoothly.
            </p>
            """, unsafe_allow_html=True)
            user = st.text_input("Username", placeholder="Enter your username")
            pw   = st.text_input("Password", placeholder="Enter your password", type="password")
            st.checkbox("Remember Me")
            submitted = st.form_submit_button("Login to Dashboard")

            if submitted:
                role = check_login(user, pw)
                if role:
                    st.session_state["authenticated"] = True
                    st.session_state["username"] = user
                    st.session_state["role"] = role
                    st.rerun()
                else:
                    st.error("Invalid username or password. Please try again.")

        return False
    return True

@st.dialog("Change My Password")
def change_password_dialog():
    new_p = st.text_input("New Password", type="password")
    if st.button("Update My Password", use_container_width=True):
        if new_p:
            update_password(st.session_state["username"], new_p)
            st.toast("Password updated successfully!", icon="✅")
            st.rerun()
        else:
            st.warning("Please enter a new password.")

@st.dialog("Create New User")
def create_user_dialog():
    with st.form("create_user_form", clear_on_submit=True):
        new_u = st.text_input("Username").strip()
        new_upw = st.text_input("Password", type="password")
        is_admin = st.checkbox("Admin Account", value=False,
                               help="Admin accounts have full access and can manage other users.")
        st.caption("Select which pages this user can access." if not is_admin
                   else "Admins automatically have access to all pages.")
        assigned_pages = st.multiselect(
            "Allowed Pages",
            options=ALL_PAGES,
            default=ALL_PAGES,
            key="create_user_pages",
            disabled=is_admin
        )

        if st.form_submit_button("Register User", use_container_width=True):
            if new_u and new_upw:
                pages = ALL_PAGES if is_admin else assigned_pages
                if create_user(new_u, new_upw, is_admin=is_admin, pages=pages):
                    st.toast(f"User {new_u} created!", icon="👤")
                    st.rerun()
                else:
                    st.error("Username already taken.")
            else:
                st.warning("All fields required.")

@st.dialog("Edit User")
def edit_user_dialog(username, current_role):
    is_currently_admin = (current_role == "admin")

    is_admin = st.checkbox("Admin Account", value=is_currently_admin,
                           key="edit_is_admin",
                           help="Admin accounts have full access and can manage other users.")
    new_pw = st.text_input("New Password (leave blank to keep current)", type="password", key="edit_pw_input")

    st.caption("Choose which pages this user can access." if not is_admin
               else "Admins automatically have access to all pages.")
    current_pages = get_user_pages(username)
    new_pages = st.multiselect(
        "Allowed Pages",
        options=ALL_PAGES,
        default=[p for p in current_pages if p in ALL_PAGES],
        key="edit_user_pages",
        disabled=is_admin
    )

    if st.button("Save Changes", key="save_edit_user", use_container_width=True):
        set_admin(username, is_admin)
        set_user_pages(username, ALL_PAGES if is_admin else new_pages)
        if new_pw.strip():
            update_password(username, new_pw.strip())
        st.toast(f"Updated {username}!", icon="✅")
        st.rerun()

def user_management_ui():
    """Main UI for users to change passwords and Admins to manage the team."""

    st.divider()
    ui_utils.icon_subheader("Account & Users", "user")

    # 1. Self-Service: Change Password (Visible to Everyone)
    if st.button("Change My Password", use_container_width=True):
        change_password_dialog()

    # 2. Admin Only: User Management
    if st.session_state.get("role") == "admin":
        ui_utils.icon_subheader("Admin Control Panel", "settings-2")

        # CREATE USER
        if st.button("Create New User", type="primary", use_container_width=True):
            create_user_dialog()

        # MANAGE USERS
        st.divider()
        ui_utils.icon_subheader("Manage Existing Users", "users")
        with sqlite3.connect(DB_NAME) as conn:
            users_df = pd.read_sql_query("SELECT username, role FROM users", conn)

        for _, row in users_df.iterrows():
            # Prevent self-deletion
            if row['username'] == st.session_state["username"]:
                continue

            is_admin_user = row['role'] == "admin"
            col_n, col_badge, col_opt = st.columns([4, 3, 2])
            col_n.write(f"**{row['username']}**")
            if is_admin_user:
                col_badge.markdown(
                    "<span style='background:#EBF5FF;color:#1565C0;border-radius:6px;"
                    "padding:2px 10px;font-size:0.78rem;font-weight:600;'>Admin</span>",
                    unsafe_allow_html=True
                )
            with col_opt:
                with st.popover("Options", use_container_width=True):
                    if st.button("Edit", key=f"edit_user_{row['username']}", use_container_width=True):
                        edit_user_dialog(row['username'], row['role'])
                    if st.button("Delete", key=f"del_user_{row['username']}", use_container_width=True):
                        delete_user(row['username'])
                        st.toast(f"Deleted {row['username']}")
                        st.rerun()