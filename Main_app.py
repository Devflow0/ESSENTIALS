import streamlit as st
import auth_manager
import security_dashboard
import reminders_page
import sqlite3
import maintenance
import REPORTS
import EXPENSE_LOGGER
import vehicle_tracker
import ui_utils
import face_dashboard


# --- 0. INITIAL CONFIG ---
st.set_page_config(page_title="Management System", layout="wide")
DB_NAME = 'alpr_data.db'

# --- 1. LOGIN GATE ---
if not auth_manager.login_page():
    st.stop()

# ─── 2. GLOBAL THEME (injected after login succeeds) ─────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    /* ═══════════════════════════════════════════════════
       ROOT / BODY
       ═══════════════════════════════════════════════════ */
    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'Inter', 'Segoe UI', sans-serif !important;
        background: #F0F4F8 !important;
    }

    /* Main content area */
    [data-testid="stMain"] {
        background: #F0F4F8 !important;
    }
    .block-container {
        padding: 2rem 2.5rem 2rem 2.5rem !important;
        max-width: 100% !important;
    }

    /* ═══════════════════════════════════════════════════
       SIDEBAR  – light panel, clean nav
       ═══════════════════════════════════════════════════ */
    [data-testid="stSidebar"] {
        background: #FFFFFF !important;
        border-right: 1px solid #E8ECF0 !important;
        padding-top: 0 !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        background: #FFFFFF !important;
        padding-top: 1.2rem !important;
    }

    /* Sidebar title (Welcome, username) */
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] .stMarkdown h1 {
        font-family: 'Inter', sans-serif !important;
        font-size: 1rem !important;
        font-weight: 700 !important;
        color: #1a1a2e !important;
        padding: 0 0.75rem !important;
        margin-bottom: 0 !important;
        letter-spacing: -0.3px;
    }

    /* Sidebar info box (role badge) */
    [data-testid="stSidebar"] [data-testid="stAlert"] {
        background: linear-gradient(135deg, #EBF5FF, #E8F0FE) !important;
        border: 1px solid #C6DAFE !important;
        border-radius: 8px !important;
        color: #1565C0 !important;
        font-size: 0.78rem !important;
        font-weight: 600 !important;
        padding: 0.4rem 0.75rem !important;
        margin: 0.3rem 0.75rem 0.8rem 0.75rem !important;
    }

    /* ── Sidebar Radio Nav Items ─────────────────────── */
    [data-testid="stSidebar"] .stRadio > label {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        color: #64748B !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        padding: 0 0.75rem !important;
        margin-bottom: 0.2rem !important;
    }

    /* Each radio option */
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.88rem !important;
        font-weight: 500 !important;
        color: #475569 !important;
        padding: 0.55rem 0.85rem !important;
        border-radius: 8px !important;
        margin-bottom: 2px !important;
        transition: all 0.18s ease;
        cursor: pointer;
    }
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:hover {
        background: #F1F5F9 !important;
        color: #1a1a2e !important;
    }

    /* Active / selected radio item */
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label[data-checked="true"],
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:has(input:checked) {
        background: #EBF5FF !important;
        color: #1565C0 !important;
        font-weight: 600 !important;
    }

    /* Hide the radio circle */
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label > div:first-child {
        display: none !important;
    }

    /* Sidebar button (Logout) */
    [data-testid="stSidebar"] .stButton > button {
        font-family: 'Inter', sans-serif !important;
        background: transparent !important;
        color: #EF4444 !important;
        border: none !important;
        font-size: 0.88rem !important;
        font-weight: 500 !important;
        padding: 0.5rem 0.85rem !important;
        border-radius: 8px !important;
        text-align: left !important;
        justify-content: flex-start !important;
        width: 100%;
        transition: all 0.18s ease;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background: #FEF2F2 !important;
    }

    /* ═══════════════════════════════════════════════════
       HEADER BAR  – hide default, style remains
       ═══════════════════════════════════════════════════ */
    [data-testid="stHeader"] {
        background: transparent !important;
    }

    /* ═══════════════════════════════════════════════════
       PAGE TITLES
       ═══════════════════════════════════════════════════ */
    h1 {
        font-family: 'Inter', sans-serif !important;
        font-size: 1.65rem !important;
        font-weight: 700 !important;
        color: #1a1a2e !important;
        letter-spacing: -0.5px;
    }
    h2 {
        font-family: 'Inter', sans-serif !important;
        font-size: 1.25rem !important;
        font-weight: 600 !important;
        color: #1a1a2e !important;
    }
    h3 {
        font-family: 'Inter', sans-serif !important;
        font-size: 1.05rem !important;
        font-weight: 600 !important;
        color: #334155 !important;
    }

    /* ═══════════════════════════════════════════════════
       METRIC CARDS (Quick Summary style)
       ═══════════════════════════════════════════════════ */
    [data-testid="stMetric"] {
        background: #FFFFFF !important;
        border: 1px solid #E8ECF0 !important;
        border-radius: 12px !important;
        padding: 1.1rem 1.3rem !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
    }
    [data-testid="stMetricLabel"] {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        color: #64748B !important;
    }
    [data-testid="stMetricValue"] {
        font-family: 'Inter', sans-serif !important;
        font-size: 1.6rem !important;
        font-weight: 700 !important;
        color: #1a1a2e !important;
    }
    [data-testid="stMetricDelta"] {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.78rem !important;
        font-weight: 500 !important;
    }

    /* ═══════════════════════════════════════════════════
       TABS  – clean underline style
       ═══════════════════════════════════════════════════ */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0 !important;
        background: transparent !important;
        border-bottom: 2px solid #E8ECF0;
    }
    .stTabs [data-baseweb="tab"] {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.88rem !important;
        font-weight: 500 !important;
        color: #64748B !important;
        padding: 0.6rem 1.2rem !important;
        border-radius: 0 !important;
        border-bottom: 2px solid transparent;
        transition: all 0.2s ease;
        background: transparent !important;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: #1565C0 !important;
    }
    .stTabs [aria-selected="true"] {
        color: #1565C0 !important;
        font-weight: 600 !important;
        border-bottom: 2px solid #1565C0 !important;
        background: transparent !important;
    }

    /* ═══════════════════════════════════════════════════
       BUTTONS  (general)
       ═══════════════════════════════════════════════════ */
    .stButton > button {
        font-family: 'Inter', sans-serif !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        font-size: 0.85rem !important;
        padding: 0.45rem 1rem !important;
        border: 1px solid #E0E0E0 !important;
        transition: all 0.2s ease;
    }
    .stButton > button:hover {
        border-color: #1565C0 !important;
        color: #1565C0 !important;
        box-shadow: 0 2px 8px rgba(21,101,192,0.12) !important;
    }

    /* Primary buttons (form submits) */
    button[kind="primary"],
    button[kind="formSubmit"] {
        background: linear-gradient(135deg, #3B82F6, #1565C0) !important;
        color: white !important;
        border: none !important;
        font-weight: 600 !important;
    }
    button[kind="primary"]:hover,
    button[kind="formSubmit"]:hover {
        background: linear-gradient(135deg, #2563EB, #0D47A1) !important;
        box-shadow: 0 4px 14px rgba(21,101,192,0.30) !important;
    }

    /* ═══════════════════════════════════════════════════
       INPUTS & TEXT FIELDS
       ═══════════════════════════════════════════════════ */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stSelectbox > div > div,
    .stDateInput > div > div > input,
    .stTimeInput > div > div > input {
        font-family: 'Inter', sans-serif !important;
        border-radius: 8px !important;
        border: 1px solid #E0E0E0 !important;
        font-size: 0.88rem !important;
        transition: border-color 0.2s ease;
    }
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: #3B82F6 !important;
        box-shadow: 0 0 0 2px rgba(59,130,246,0.15) !important;
    }
    .stTextInput label,
    .stTextArea label,
    .stSelectbox label,
    .stDateInput label,
    .stTimeInput label {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        color: #475569 !important;
    }

    /* ═══════════════════════════════════════════════════
       EXPANDERS
       ═══════════════════════════════════════════════════ */
    .streamlit-expanderHeader {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.92rem !important;
        font-weight: 600 !important;
        color: #334155 !important;
        background: #FFFFFF !important;
        border-radius: 8px !important;
    }
    [data-testid="stExpander"] {
        background: #FFFFFF !important;
        border: 1px solid #E8ECF0 !important;
        border-radius: 10px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.03) !important;
    }

    /* ═══════════════════════════════════════════════════
       DATA TABLES
       ═══════════════════════════════════════════════════ */
    .stDataFrame {
        border-radius: 10px !important;
        overflow: hidden;
        border: 1px solid #E8ECF0 !important;
    }
    [data-testid="stDataFrame"] th {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.78rem !important;
        font-weight: 600 !important;
        color: #64748B !important;
        text-transform: uppercase;
        letter-spacing: 0.3px;
        background: #F8FAFC !important;
    }
    [data-testid="stDataFrame"] td {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.85rem !important;
        color: #334155 !important;
    }

    /* ═══════════════════════════════════════════════════
       TOAST / ALERTS
       ═══════════════════════════════════════════════════ */
    [data-testid="stAlert"] {
        font-family: 'Inter', sans-serif !important;
        border-radius: 10px !important;
        font-size: 0.88rem !important;
    }

    /* ═══════════════════════════════════════════════════
       FORMS  (general, non-login forms)
       ═══════════════════════════════════════════════════ */
    [data-testid="stForm"] > div:first-child {
        background: #FFFFFF !important;
        border: 1px solid #E8ECF0 !important;
        border-radius: 12px !important;
        padding: 1.2rem !important;
        box-shadow: 0 1px 4px rgba(0,0,0,0.04) !important;
    }

    /* ═══════════════════════════════════════════════════
       DIVIDERS
       ═══════════════════════════════════════════════════ */
    hr {
        border-color: #E8ECF0 !important;
        opacity: 0.6;
    }

    /* ═══════════════════════════════════════════════════
       SCROLLBAR
       ═══════════════════════════════════════════════════ */
    ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }
    ::-webkit-scrollbar-track {
        background: transparent;
    }
    ::-webkit-scrollbar-thumb {
        background: #CBD5E1;
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #94A3B8;
    }

    /* ═══════════════════════════════════════════════════
       MISC POLISH
       ═══════════════════════════════════════════════════ */
    .stMarkdown p, .stMarkdown li {
        font-family: 'Inter', sans-serif !important;
        color: #475569;
        font-size: 0.9rem;
        line-height: 1.6;
    }
    .stCaption, .stMarkdown .caption {
        color: #94A3B8 !important;
        font-size: 0.78rem !important;
    }

    /* Checkbox label */
    .stCheckbox label {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.85rem !important;
        color: #475569 !important;
    }

    /* File uploader */
    [data-testid="stFileUploader"] {
        border-radius: 10px !important;
    }

    footer { display: none !important; }
</style>
""", unsafe_allow_html=True)

# --- 3. USER-ASSIGNED NAVIGATION ---
role = st.session_state.get("role", "staff")
user_name = st.session_state.get("username", "User")

st.sidebar.title(f"Welcome, {user_name.capitalize()}")

# Load page list assigned to this user by the admin (admins get everything)
menu_options = auth_manager.get_user_pages(user_name)
if not menu_options:
    st.warning("No pages have been assigned to your account. Please contact an administrator.")
    st.stop()


# --- 3b. CSS FOR SIDEBAR ICONS ---
icon_css = ""
icon_map = {
    "Security Dashboard": "shield",
    "Face Recognition": "users",
    "Airport Reminders": "plane",
    "Expenses": "wallet",
    "Vehicle Tracker": "truck",
    "Maintenance": "wrench",
    "Logbook": "file-text",
    "Admin Settings": "settings"
}

for i, label in enumerate(menu_options):
    icon = icon_map.get(label)
    if icon:
        b64 = ui_utils.get_icon_base64(icon)
        if b64:
            icon_css += f"""
            [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:nth-of-type({i+1})::before {{
                content: "";
                display: inline-block;
                width: 18px;
                height: 18px;
                margin-right: 12px;
                vertical-align: middle;
                background-color: #475569;
                -webkit-mask-image: url('data:image/svg+xml;base64,{b64}');
                mask-image: url('data:image/svg+xml;base64,{b64}');
                -webkit-mask-repeat: no-repeat;
                mask-repeat: no-repeat;
                -webkit-mask-size: contain;
                mask-size: contain;
            }}
            [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:nth-of-type({i+1})[data-checked="true"]::before,
            [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:nth-of-type({i+1}):has(input:checked)::before {{
                background-color: #1565C0;
            }}
            """

st.markdown(f"<style>{icon_css}</style>", unsafe_allow_html=True)

choice = st.sidebar.radio("Navigate To:", menu_options)

# Divider before logout
st.sidebar.markdown("---")
if st.sidebar.button("Logout"):
    st.session_state["authenticated"] = False
    st.rerun()

# --- 4. PAGE ROUTING ---
if choice == "Security Dashboard":
    security_dashboard.security_ui()

elif choice == "Face Recognition":
    face_dashboard.face_ui()

elif choice == "Vehicle Tracker":
    vehicle_tracker.vehicle_tracker_ui()

elif choice == "Airport Reminders":
    reminders_page.reminders_ui()

elif choice == "Expenses":
    EXPENSE_LOGGER.expense_ui()

elif choice == "Maintenance":
    maintenance.maintenance_ui()

elif choice == "Logbook":
    REPORTS.reports_ui()

elif choice == "Admin Settings":
    ui_utils.icon_header("System Administration", "settings")
    # Only Admin can manage users
    auth_manager.user_management_ui()
