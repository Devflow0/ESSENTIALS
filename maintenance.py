import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import ui_utils

DB_NAME = 'alpr_data.db'

# --- DATABASE LOGIC ---
def init_maintenance_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS maintenance_tickets 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, 
             date_reported TEXT, 
             area TEXT, 
             description TEXT, 
             priority TEXT, 
             assigned_to TEXT, 
             status TEXT)''')
        conn.commit()

@st.dialog("Maintenance Work Order")
def maintenance_form_dialog(edit_id=None, m_data=None):
    if m_data is None:
        m_data = {}
    is_editing = edit_id is not None

    with st.form("maintenance_form", clear_on_submit=not is_editing):
        col1, col2 = st.columns(2)
        with col1:
            area = st.text_input("Area / Room Number", value=m_data.get('area', ""), placeholder="e.g. Room 304 or Lobby")
            priority = st.selectbox("Priority Level", ["Low", "Medium", "High", "URGENT"], 
                                    index=["Low", "Medium", "High", "URGENT"].index(m_data.get('priority', 'Low')))
        with col2:
            tech = st.text_input("Assigned Technician", value=m_data.get('assigned_to', ""), placeholder="Name of staff")
            status = st.selectbox("Current Status", ["Pending", "In Progress", "Resolved", "On Hold"],
                                  index=["Pending", "In Progress", "Resolved", "On Hold"].index(m_data.get('status', 'Pending')))
        
        desc = st.text_area("Issue Description", value=m_data.get('description', ""), placeholder="Details of the fault...")
        
        btn_label = "Update Work Order" if is_editing else "Submit Work Order"
        if st.form_submit_button(btn_label, use_container_width=True):
            if area and desc:
                with sqlite3.connect(DB_NAME) as conn:
                    if is_editing:
                        conn.execute('''UPDATE maintenance_tickets SET area=?, description=?, priority=?, assigned_to=?, status=? WHERE id=?''',
                                     (area, desc, priority, tech, status, edit_id))
                        st.toast("Work order updated!", icon="✏️")
                    else:
                        conn.execute('''INSERT INTO maintenance_tickets (date_reported, area, description, priority, assigned_to, status) 
                                        VALUES (?, ?, ?, ?, ?, ?)''', 
                                     (datetime.now().strftime("%Y-%m-%d %H:%M"), area, desc, priority, tech, status))
                        st.toast("Work order created!", icon="🛠️")
                st.rerun()
            else:
                st.warning("Please fill in the Area and Description.")

# --- UI LOGIC ---
def maintenance_ui():
    init_maintenance_db()

    # --- CSS FOR ALL ICONS ---
    icons = {
        "wrench":    ui_utils.get_icon_base64("wrench"),
        "clipboard": ui_utils.get_icon_base64("clipboard-list"),
        "pencil":    ui_utils.get_icon_base64("pencil"),
        "check":     ui_utils.get_icon_base64("check-circle"),
        "trash":     ui_utils.get_icon_base64("trash"),
        "plus":      ui_utils.get_icon_base64("plus"),
        "save":      ui_utils.get_icon_base64("save"),
        "pin":       ui_utils.get_icon_base64("map-pin"),
        "alert":     ui_utils.get_icon_base64("alert-triangle"),
        "user":      ui_utils.get_icon_base64("user"),
        "tag":       ui_utils.get_icon_base64("tag"),
        "notes":     ui_utils.get_icon_base64("file-text"),
        "list":      ui_utils.get_icon_base64("list"),
        "history":   ui_utils.get_icon_base64("check-circle")
    }

    icon_css = f"""
    <style>
    /* 1. Main Action Button */
    button:has(p:contains("Report New Issue")) p::before {{
        content: ""; display: inline-block; width: 18px; height: 18px; margin-right: 10px; vertical-align: middle;
        background-color: white; -webkit-mask: url('data:image/svg+xml;base64,{icons["wrench"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["wrench"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}

    /* 2. Tabs */
    [data-testid="stTabs"] button:nth-of-type(1) p::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 8px; vertical-align: middle;
        background-color: currentColor; -webkit-mask: url('data:image/svg+xml;base64,{icons["list"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["list"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    [data-testid="stTabs"] button:nth-of-type(2) p::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 8px; vertical-align: middle;
        background-color: currentColor; -webkit-mask: url('data:image/svg+xml;base64,{icons["history"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["history"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}

    /* 3. Action Buttons in Cards */
    button:has(p:contains("Edit")) p::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: middle;
        background-color: currentColor; -webkit-mask: url('data:image/svg+xml;base64,{icons["pencil"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["pencil"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    button:has(p:contains("Done")) p::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: middle;
        background-color: #059669; -webkit-mask: url('data:image/svg+xml;base64,{icons["check"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["check"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    button:has(p:contains("Delete")) p::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: middle;
        background-color: #EF4444; -webkit-mask: url('data:image/svg+xml;base64,{icons["trash"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["trash"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}

    /* 4. Form Submit Buttons */
    button[kind="formSubmit"]:has(p:contains("Update")) p::before {{
        content: ""; display: inline-block; width: 16px; height: 16px; margin-right: 8px; vertical-align: middle;
        background-color: white; -webkit-mask: url('data:image/svg+xml;base64,{icons["save"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["save"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    button[kind="formSubmit"]:has(p:contains("Submit")) p::before {{
        content: ""; display: inline-block; width: 16px; height: 16px; margin-right: 8px; vertical-align: middle;
        background-color: white; -webkit-mask: url('data:image/svg+xml;base64,{icons["plus"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["plus"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}

    /* 5. Input Labels */
    [data-testid="stTextInput"]:has(label:contains("Area")) label::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: middle;
        background-color: #475569; -webkit-mask: url('data:image/svg+xml;base64,{icons["pin"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["pin"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    [data-testid="stSelectbox"]:has(label:contains("Priority")) label::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: middle;
        background-color: #475569; -webkit-mask: url('data:image/svg+xml;base64,{icons["alert"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["alert"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    [data-testid="stTextInput"]:has(label:contains("Technician")) label::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: middle;
        background-color: #475569; -webkit-mask: url('data:image/svg+xml;base64,{icons["user"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["user"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    [data-testid="stSelectbox"]:has(label:contains("Status")) label::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: middle;
        background-color: #475569; -webkit-mask: url('data:image/svg+xml;base64,{icons["tag"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["tag"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    [data-testid="stTextArea"]:has(label:contains("Description")) label::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: middle;
        background-color: #475569; -webkit-mask: url('data:image/svg+xml;base64,{icons["notes"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["notes"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    </style>
    """
    st.markdown(icon_css, unsafe_allow_html=True)

    ui_utils.icon_header("Facility Maintenance & Work Orders", "wrench")

    # --- SECTION 1: REPORT NEW ISSUE ---
    if st.button("Report New Issue", type="primary", use_container_width=True):
        maintenance_form_dialog()

    st.divider()

    # --- SECTION 2: MAINTENANCE DASHBOARD ---
    ui_utils.icon_subheader("Work Order Dashboard", "clipboard-list")
    
    with sqlite3.connect(DB_NAME) as conn:
        df = pd.read_sql_query("SELECT * FROM maintenance_tickets", conn)

    if not df.empty:
        # Tabs for different statuses
        tab_active, tab_resolved = st.tabs(["Active Issues", "Resolved History"])
        
        with tab_active:
            active_df = df[df['status'] != "Resolved"].sort_values(by="priority", ascending=False)
            display_tickets(active_df)
            
        with tab_resolved:
            resolved_df = df[df['status'] == "Resolved"].sort_values(by="date_reported", ascending=False)
            display_tickets(resolved_df, is_history=True)
    else:
        st.info("No maintenance tickets found.")

def display_tickets(df, is_history=False):
    if df.empty:
        st.caption("No tickets in this category.")
        return

    for _, row in df.iterrows():
        # Color coding priority labels
        p_colors = {"Low": "blue", "Medium": "green", "High": "orange", "URGENT": "red"}
        p_color = p_colors.get(row['priority'], "grey")
        
        with st.container():
            c1, c2, c3 = st.columns([1, 2.5, 1.5])
            with c1:
                st.write(f"**{row['area']}**")
                st.caption(f"Date Reported: {row['date_reported']}")
                st.markdown(f":{p_color}[**{row['priority']}**]")
            
            with c2:
                st.write(row['description'])
                st.caption(f"Assigned Technician: {row['assigned_to'] if row['assigned_to'] else 'Unassigned'}")
                st.info(f"Status: {row['status']}")

            with c3:
                # 3 Columns for Edit, Resolve, and Delete
                sc1, sc2, sc3 = st.columns(3)
                
                # EDIT
                if sc1.button("Edit", key=f"edit_m_{row['id']}", use_container_width=True):
                    maintenance_form_dialog(row['id'], row.to_dict())
                
                # RESOLVE (CHECKMARK) - Only show if not already resolved
                if not is_history:
                    if sc2.button("Done", key=f"res_m_{row['id']}", use_container_width=True):
                        with sqlite3.connect(DB_NAME) as conn:
                            conn.execute("UPDATE maintenance_tickets SET status = 'Resolved' WHERE id = ?", (row['id'],))
                        st.toast(f"Issue in {row['area']} marked as Resolved!", icon="✅")
                        st.rerun()
                else:
                    sc2.write("") # Placeholder for history tab
                
                # DELETE
                if sc3.button("Delete", key=f"del_m_{row['id']}", use_container_width=True):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("DELETE FROM maintenance_tickets WHERE id=?", (row['id'],))
                    st.rerun()
            st.divider()