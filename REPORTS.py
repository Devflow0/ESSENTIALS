import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import ui_utils

DB_NAME = 'alpr_data.db'

# --- DATABASE LOGIC ---
def init_reports_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS incident_reports 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, 
             timestamp TEXT, 
             category TEXT, 
             title TEXT, 
             description TEXT, 
             reported_by TEXT, 
             status TEXT)''')
        conn.commit()

@st.dialog("Create New Log Entry")
def log_entry_dialog():
    with st.form("log_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            category = st.selectbox("Category", [
                "Shift Handover", 
                "Security Incident", 
                "Lost & Found", 
                "Guest Complaint", 
                "General Observation",
                "Emergency"
            ])
            title = st.text_input("Subject / Title", placeholder="Brief summary")
        with col2:
            reporter = st.text_input("Reported By", value=st.session_state.get("username", ""))
            status = st.selectbox("Flag Level", ["Routine", "Follow-up Required", "Resolved"])

        description = st.text_area("Detailed Report", placeholder="Describe the event in detail...")

        if st.form_submit_button("Lock Entry to Logbook", use_container_width=True):
            if title and description:
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute('''INSERT INTO incident_reports (timestamp, category, title, description, reported_by, status) 
                                    VALUES (?, ?, ?, ?, ?, ?)''', 
                                 (datetime.now().strftime("%Y-%m-%d %H:%M"), category, title, description, reporter, status))
                st.toast("Entry logged successfully!", icon="📝")
                st.rerun()
            else:
                st.warning("Title and Description are required.")

# --- UI LOGIC ---
def reports_ui():
    init_reports_db()
    ui_utils.icon_header("Digital Logbook & Incident Reports", "file-text")
    st.markdown("Centralized record for shift handovers, incidents, and observations.")

    # --- SECTION 1: CREATE NEW LOG ENTRY ---
    if st.button("Create New Log Entry", type="primary", use_container_width=True):
        log_entry_dialog()

    st.divider()

    # --- SECTION 2: VIEW & SEARCH LOGS ---
    ui_utils.icon_subheader("Logbook Explorer", "list")
    
    # Search Filters
    f1, f2, f3 = st.columns([2, 1, 1])
    search_term = f1.text_input("Search description or title...", placeholder="e.g. 'keys' or 'Room 201'")
    cat_filter = f2.selectbox("Filter Category", ["All", "Shift Handover", "Security Incident", "Lost & Found", "Guest Complaint", "General Observation", "Emergency"])
    sort_order = f3.selectbox("Sort By", ["Newest First", "Oldest First"])

    # Fetch Data
    with sqlite3.connect(DB_NAME) as conn:
        query = "SELECT * FROM incident_reports WHERE 1=1"
        params = []
        if cat_filter != "All":
            query += " AND category = ?"
            params.append(cat_filter)
        if search_term:
            query += " AND (description LIKE ? OR title LIKE ?)"
            params.extend([f'%{search_term}%', f'%{search_term}%'])
        
        df = pd.read_sql_query(query, conn, params=params)

    if not df.empty:
        # Sort logic
        df = df.sort_values(by="timestamp", ascending=(sort_order == "Oldest First"))

        for _, row in df.iterrows():
            # Styling for different flags
            bg_color = "#f0f2f6"
            if row['status'] == "Follow-up Required": bg_color = "#fff4e6"
            if row['category'] == "Emergency": bg_color = "#ffe3e3"

            with st.container():
                st.markdown(f"""<div style="background-color:{bg_color}; padding:15px; border-radius:10px; border-left: 5px solid #3366ff; margin-bottom:10px;"><span style="font-size: 0.8em; color: grey;">{row['timestamp']} | <b>{row['category']}</b></span><h4 style="margin: 5px 0;">{row['title']}</h4><p style="font-size: 0.95em;">{row['description']}</p><span style="font-size: 0.8em;"><b>Reporter:</b> {row['reported_by']} | <b>Status:</b> {row['status']}</span></div>""", unsafe_allow_html=True)
                
                # Admin/Security can delete or resolve
                if st.session_state.get("role") in ["admin", "security"]:
                    c1, c2, _ = st.columns([1, 1, 4])
                    if row['status'] != "Resolved":
                        if c1.button("Mark Resolved", key=f"res_log_{row['id']}"):
                            with sqlite3.connect(DB_NAME) as conn:
                                conn.execute("UPDATE incident_reports SET status = 'Resolved' WHERE id = ?", (row['id'],))
                            st.rerun()
                    if st.session_state.get("role") == "admin":
                        if c2.button("Delete", key=f"del_log_{row['id']}"):
                            with sqlite3.connect(DB_NAME) as conn:
                                conn.execute("DELETE FROM incident_reports WHERE id = ?", (row['id'],))
                            st.rerun()
    else:
        st.info("No logs found for the selected criteria.")