import streamlit as st
import cv2
import sqlite3
import pandas as pd
import plotly.express as px
import requests
from datetime import datetime, timedelta
from ai_helper import get_ai_daily_summary
import ui_utils
from db_security import decrypt_data, decrypt_bytes
import os
import socket

def get_local_ip():
    """Dynamically detects the server's local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        # We don't actually need to reach this IP, it's just to trigger the OS to pick an interface
        s.connect(('8.8.8.8', 1))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "localhost"
    return local_ip


DB_NAME = 'alpr_data.db'
SERVER_IP = get_local_ip()
SERVER_URL = f"http://{SERVER_IP}:8000" # FastAPI vision_server URL

def get_decrypted_image(path):
    """Loads an encrypted image from disk and decrypts it."""
    if path and os.path.exists(path):
        try:
            with open(path, 'rb') as f:
                encrypted_bytes = f.read()
            return decrypt_bytes(encrypted_bytes)
        except:
            return None
    return None

# --- DATA FETCHING ---
def init_security_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS movements 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, vehicle_id INTEGER, event TEXT, 
             timestamp DATETIME, plate TEXT, snapshot_path TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS watchlist 
            (plate TEXT PRIMARY KEY, reason TEXT, added_on DATETIME)''')

        # ── Vehicle Profiles table ────────────────────────────────────
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vehicle_profiles (
                plate               TEXT PRIMARY KEY,
                first_seen          DATETIME,
                last_seen           DATETIME,
                total_visits        INTEGER DEFAULT 0,
                total_entries       INTEGER DEFAULT 0,
                total_exits         INTEGER DEFAULT 0,
                notes               TEXT DEFAULT '',
                last_snapshot_path  TEXT DEFAULT ''
            )
        ''')
        conn.commit()

    # ── One-time migration: back-fill profiles from existing movements ─
    _migrate_profiles_from_movements()


def _migrate_profiles_from_movements():
    """Populates vehicle_profiles from the movements table for any plate not yet profiled."""
    with sqlite3.connect(DB_NAME) as conn:
        raw = pd.read_sql_query("SELECT plate, event, timestamp, snapshot_path FROM movements", conn)

    if raw.empty:
        return

    raw['plate_dec'] = raw['plate'].apply(decrypt_data)
    raw['timestamp'] = pd.to_datetime(raw['timestamp'])

    grouped = raw.groupby('plate_dec')
    with sqlite3.connect(DB_NAME) as conn:
        for plate, grp in grouped:
            first_seen  = grp['timestamp'].min().strftime('%Y-%m-%d %H:%M:%S')
            last_seen   = grp['timestamp'].max().strftime('%Y-%m-%d %H:%M:%S')
            total       = len(grp)
            entries     = len(grp[grp['event'] == 'ENTRY'])
            exits       = len(grp[grp['event'] == 'EXIT'])
            last_snap   = grp.sort_values('timestamp').iloc[-1]['snapshot_path']
            conn.execute('''
                INSERT INTO vehicle_profiles
                    (plate, first_seen, last_seen, total_visits, total_entries, total_exits, last_snapshot_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plate) DO NOTHING
            ''', (plate, first_seen, last_seen, total, entries, exits, last_snap))

def get_analytics_data():
    """Fetches all movement data from the DB for real-time analysis."""
    with sqlite3.connect(DB_NAME) as conn:
        df = pd.read_sql_query("SELECT * FROM movements", conn)
    
    if not df.empty:
        df['plate'] = df['plate'].apply(decrypt_data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        df['date'] = df['timestamp'].dt.date
        df['hour'] = df['timestamp'].dt.hour
        df['day_name'] = df['timestamp'].dt.day_name()
    return df

@st.fragment
def vehicle_intel_fragment():
    """Unified vehicle intelligence panel: profiles, movement history, snapshots."""

    # ── Single search bar and manual refresh ─────────────────────────
    vc1, vc2 = st.columns([5, 1])
    with vc1:
        search = st.text_input(
            "Search vehicle", key="vi_search",
            placeholder="Type a plate to filter… (e.g. ABC123)",
            label_visibility="collapsed"
        ).upper().strip()
    with vc2:
        if st.button("🔄 Refresh", key="btn_vi_refresh", use_container_width=True):
            st.session_state.pop("_vehicle_intel_cache", None)
            st.rerun()

    # ── Load profiles (cached until Refresh is clicked) ──────────────
    if "_vehicle_intel_cache" not in st.session_state:
        with sqlite3.connect(DB_NAME) as conn:
            st.session_state["_vehicle_intel_cache"] = pd.read_sql_query(
                "SELECT plate, first_seen, last_seen, total_visits, total_entries, total_exits "
                "FROM vehicle_profiles ORDER BY last_seen DESC",
                conn
            )
            
    profiles = st.session_state["_vehicle_intel_cache"]

    if profiles.empty:
        st.info("No vehicle profiles yet. They are built automatically as vehicles are detected.")
        return

    filtered = profiles[profiles['plate'].str.contains(search, na=False)] if search else profiles
    st.caption(f"{len(filtered)} of {len(profiles)} vehicle(s) shown")

    # ── Two-column layout: profile table | detail panel ──────────────
    left, right = st.columns([1.4, 2])

    with left:
        ui_utils.icon_subheader("Known Vehicles", "car")
        sel = st.dataframe(
            filtered.rename(columns={
                "plate": "Plate", "first_seen": "First Seen", "last_seen": "Last Seen",
                "total_visits": "Visits", "total_entries": "In", "total_exits": "Out"
            })[["Plate", "Last Seen", "Visits", "In", "Out"]],
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="vi_profile_table"
        )

    with right:
        # Determine selected plate (from row click or search if only 1 result)
        selected_plate = None
        if sel and sel.selection.rows and not filtered.empty and sel.selection.rows[0] < len(filtered):
            selected_plate = filtered.iloc[sel.selection.rows[0]]['plate']
        elif len(filtered) == 1:
            selected_plate = filtered.iloc[0]['plate']

        if selected_plate:
            ui_utils.icon_subheader(f"{selected_plate}", "shield")

            # Pull profile stats
            vrow = profiles[profiles['plate'] == selected_plate].iloc[0]
            s1, s2, s3 = st.columns(3)
            s1.metric("Total Visits", int(vrow['total_visits']))
            s2.metric("Entries", int(vrow['total_entries']))
            s3.metric("Exits", int(vrow['total_exits']))
            st.caption(f"First seen: {vrow['first_seen']}  ·  Last seen: {vrow['last_seen']}")

            # Pull all movements for this vehicle
            with sqlite3.connect(DB_NAME) as conn:
                raw_moves = pd.read_sql_query(
                    "SELECT event, timestamp, snapshot_path, plate FROM movements ORDER BY id DESC",
                    conn
                )
            if not raw_moves.empty:
                raw_moves['plate_dec'] = raw_moves['plate'].apply(decrypt_data)
                history = raw_moves[raw_moves['plate_dec'] == selected_plate][['timestamp', 'event', 'snapshot_path']].copy()
                history['timestamp'] = pd.to_datetime(history['timestamp'])
                history = history.sort_values('timestamp', ascending=False)

                if not history.empty:
                    # Row click in movement log → show that snapshot
                    log_sel = st.dataframe(
                        history.rename(columns={"timestamp": "Time", "event": "Event", "snapshot_path": "Snapshot"}),
                        use_container_width=True,
                        hide_index=True,
                        on_select="rerun",
                        selection_mode="single-row",
                        key=f"vi_history_table_{selected_plate}",
                        height=220
                    )

                    # Snapshot viewer
                    snap_path = None
                    if log_sel and log_sel.selection.rows:
                        snap_path = history.iloc[log_sel.selection.rows[0]]['snapshot_path']
                    else:
                        # Default to latest
                        with sqlite3.connect(DB_NAME) as conn:
                            row = conn.execute(
                                "SELECT last_snapshot_path FROM vehicle_profiles WHERE plate=?",
                                (selected_plate,)
                            ).fetchone()
                        snap_path = row[0] if row else None

                    if snap_path:
                        img = get_decrypted_image(snap_path)
                        if img:
                            st.image(img, caption=f"Snapshot · {selected_plate}", use_container_width=True)
        else:
            st.info("← Select a vehicle from the table to view its full history and snapshots.")

    # ── Recent captures strip (bottom) ───────────────────────────────
    st.divider()
    ui_utils.icon_subheader("Recent Captures", "camera")
    raw_df = get_analytics_data()
    recent = raw_df.sort_values('timestamp', ascending=False).head(4)
    if not recent.empty:
        caps = st.columns(4)
        for i, (_, row) in enumerate(recent.iterrows()):
            with caps[i]:
                img = get_decrypted_image(row['snapshot_path'])
                if img:
                    st.image(img, caption=f"{row['plate']} · {row['event']}", use_container_width=True)
                else:
                    st.caption(f"No image · {row['plate']}")


# --- DIALOGS ---
@st.dialog("Add to Watchlist")
def add_watchlist_dialog():
    with st.form("add_wl_form"):

        plate = st.text_input("Plate Number").upper()
        reason = st.text_input("Reason for Watchlist")
        if st.form_submit_button("Add to Watchlist"):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT OR REPLACE INTO watchlist (plate, reason, added_on) VALUES (?, ?, ?)",
                             (plate, reason, datetime.now()))
            st.success(f"Added {plate} to watchlist")
            st.rerun()
@st.dialog("Current Watchlist")
def view_watchlist_dialog():
    with sqlite3.connect(DB_NAME) as conn:

        wl = pd.read_sql_query("SELECT * FROM watchlist", conn)
    if not wl.empty:
        st.dataframe(wl, use_container_width=True, hide_index=True)
    else:
        st.info("Watchlist is currently empty.")

# --- LIVE FRAGMENTS ---
@st.fragment(run_every=1.0)
def alert_listener():
    """Polls for watchlist alerts every second."""
    try:
        response = requests.get(f"{SERVER_URL}/alerts", timeout=0.5)
        if response.status_code == 200:
            alerts = response.json().get("alerts", [])
            for alert in alerts:
                st.toast(f"ALERT: {alert['plate']} detected!", icon="🚩") # st.toast icon must be emoji or None
    except: pass

@st.fragment(run_every=2.0)
def live_monitor_fragment():
    """Displays the Video Stream and Recent Logs."""
    col_log, col_vid = st.columns([1, 2.5])
    with col_vid:
        v_col1, v_col2 = st.columns(2)
        with v_col1:
            st.image(f"{SERVER_URL}/video_entry", use_container_width=True, caption="Entry Gate Camera")
        with v_col2:
            st.image(f"{SERVER_URL}/video_exit", use_container_width=True, caption="Exit Gate Camera")
    with col_log:
        ui_utils.icon_subheader("Recent Movements", "clock")
        with sqlite3.connect(DB_NAME) as conn:
            logs = pd.read_sql_query("SELECT event, plate, timestamp FROM movements ORDER BY id DESC LIMIT 10", conn)
            logs['plate'] = logs['plate'].apply(decrypt_data)
            st.dataframe(logs, hide_index=True, use_container_width=True)


# --- AUTO-UPDATING ANALYTICS FRAGMENT ---
@st.fragment(run_every=5.0) # <--- Auto-updates every 5 seconds
def analytics_fragment(date_range):
    """Calculates and renders metrics/charts based on the latest DB data."""
    raw_df = get_analytics_data()
    
    if raw_df.empty:
        st.info("No movement data available yet.")
        return

    # Apply Filtering
    if len(date_range) == 2:
        start_date, end_date = date_range
        df = raw_df[(raw_df['date'] >= start_date) & (raw_df['date'] <= end_date)].copy()
        
        if df.empty:
            st.warning("No data found for this range.")
            return

        # 1. LIVE METRICS
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Movements", len(df))
        m2.metric("Unique Vehicles", df['plate'].nunique())
        m3.metric("Entries", len(df[df['event']=='ENTRY']))
        m4.metric("Exits", len(df[df['event']=='EXIT']))

        st.divider()

        # 2. INTERACTIVE CHARTS
        ch1, ch2 = st.columns(2)
        with ch1:
            hourly = df.groupby('hour').size().reset_index(name='counts')
            st.plotly_chart(px.bar(hourly, x='hour', y='counts', title="Traffic by Hour", 
                                   template="plotly_white", color_discrete_sequence=['#3366ff']), 
                            use_container_width=True, key="hour_chart")
        with ch2:
            day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            daily = df.groupby('day_name').size().reindex(day_order).reset_index(name='counts')
            st.plotly_chart(px.line(daily, x='day_name', y='counts', title="Traffic by Day", 
                                    markers=True, template="plotly_white", color_discrete_sequence=['#ff4b4b']), 
                            use_container_width=True, key="day_chart")

        ch3, ch4 = st.columns(2)
        with ch3:
            top = df['plate'].value_counts().nlargest(10).reset_index()
            top.columns = ['Plate', 'Visits']
            fig_top = px.bar(top, x='Visits', y='Plate', orientation='h', title="Frequent Visitors", template="plotly_white")
            fig_top.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_top, use_container_width=True, key="freq_chart")
        with ch4:
            trend = df.groupby(['date', 'event']).size().reset_index(name='count')
            st.plotly_chart(px.area(trend, x='date', y='count', color='event', title="Volume Trend", 
                                    template="plotly_white", color_discrete_map={'ENTRY': '#00CC96', 'EXIT': '#EF553B'}), 
                            use_container_width=True, key="trend_chart")

# 1. Custom CSS for the Floating Action Button (FAB)
st.markdown("""
    <style>
    .fab-container {
        position: fixed;
        bottom: 30px;
        right: 30px;
        z-index: 999;
    }
    .fab-button {
        background-color: #3366ff;
        color: white;
        border-radius: 50%;
        width: 60px;
        height: 60px;
        border: none;
        box-shadow: 0px 4px 10px rgba(0,0,0,0.3);
        cursor: pointer;
        font-size: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: transform 0.2s;
    }
    .fab-button:hover {
        transform: scale(1.1);
        background-color: #254eda;
    }
    </style>
""", unsafe_allow_html=True)

@st.dialog("AI Vehicle Intelligence")
def show_ai_summary():
    ui_utils.icon_subheader("Ask the Security AI", "zap")

    st.markdown(
        "Type a question about any vehicle, plate, or traffic pattern — or leave blank "
        "to get today's automatic daily summary."
    )

    user_prompt = st.text_area(
        "Your question",
        placeholder=(
            "e.g.  Tell me more information about plate ABC123\n"
            "      How many times did vehicle XYZ enter this week?\n"
            "      Which vehicle visited most frequently last month?"
        ),
        height=120,
        key="ai_prompt_input"
    )

    col_run, col_summary = st.columns(2)
    run_custom  = col_run.button("Ask AI", type="primary",     use_container_width=True)
    run_summary = col_summary.button("Today's Summary", use_container_width=True)

    if run_custom or run_summary:
        prompt_to_use = user_prompt.strip() if run_custom and user_prompt.strip() else None
        label = "Answering your question…" if prompt_to_use else "Generating daily summary…"
        with st.spinner(label):
            result = get_ai_daily_summary(custom_prompt=prompt_to_use)
        st.divider()
        st.markdown(result)
        st.caption(f"Generated at {datetime.now().strftime('%H:%M')}")

# --- MAIN UI ---
def security_ui(): # Ensure this has NO leading spaces (top-level)
    init_security_db()
    
    # Start background alert polling
    alert_listener()
    ui_utils.icon_header("Security & ALPR Monitoring", "shield")
    
    # Static Controls
    c1, c2, c3 = st.columns(3)
    if c1.button("Add Watchlist", use_container_width=True):
        add_watchlist_dialog()
    if c2.button("View Watchlist", use_container_width=True):
        view_watchlist_dialog()
    if c3.button("🤖 AI Query", use_container_width=True, help="Ask the AI about any vehicle or traffic pattern"):
        show_ai_summary()
    
    st.divider()

    # Section 1: Live Feed (Auto-refreshes every 2s)
    live_monitor_fragment()

    st.divider()


    # Section 2: Analytics (Auto-refreshes every 5s)
    ui_utils.icon_subheader("Real-Time ALPR Analytics", "bar-chart")
    
    # We keep the Date Input OUTSIDE the fragment so user interaction is smooth
    with sqlite3.connect(DB_NAME) as conn:
        db_dates = pd.read_sql_query("SELECT timestamp FROM movements", conn)
    
    if db_dates.empty:
        st.info("Start the stream to collect analytics data.")
        return

    # Setup date selection
    all_dates = pd.to_datetime(db_dates['timestamp']).dt.date
    min_d, max_d = all_dates.min(), all_dates.max()
    
    if 'alpr_date_range' not in st.session_state:
        st.session_state['alpr_date_range'] = (max(min_d, max_d - timedelta(days=30)), max_d)

    date_range = st.date_input("Analytics Range", value=st.session_state['alpr_date_range'],
                               min_value=min_d, max_value=max_d)
    
    if date_range != st.session_state['alpr_date_range']:
        st.session_state['alpr_date_range'] = date_range
        st.rerun()

    # Call the auto-updating fragment
    analytics_fragment(date_range)

    # Section 3: Unified Vehicle Intelligence
    with st.expander("🚗  Vehicle Intelligence", expanded=True):
        vehicle_intel_fragment()