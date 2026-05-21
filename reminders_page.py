import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import ui_utils
import urllib.parse

DB_NAME = 'alpr_data.db'

# --- DATABASE LOGIC ---
def init_reminders_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS reminders 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, 
             date TEXT, time TEXT, occupant TEXT, destination TEXT, 
             description TEXT, priority TEXT, driver_phone TEXT, 
             has_amount INTEGER, amount TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS drivers 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, 
             name TEXT, phone TEXT, category TEXT)''')
        conn.commit()

@st.dialog("Driver Details")
def driver_form_dialog(edit_id=None, d_data=None):
    if d_data is None: d_data = {}
    is_editing_driver = edit_id is not None
    
    d_col1, d_col2, d_col3 = st.columns([2, 2, 1])
    
    new_d_name = d_col1.text_input("Driver Name", value=d_data.get('name', ""))
    new_d_phone = d_col2.text_input("Phone (e.g. 234...)", value=d_data.get('phone', ""))
    
    categories = ["BWG", "BWA", "JWH", "BWH"]
    current_cat_idx = categories.index(d_data.get('category', "BWG")) if is_editing_driver and d_data.get('category') in categories else 0
    new_d_cat = d_col3.selectbox("Category", categories, index=current_cat_idx)
    
    btn_label = "Update Driver" if is_editing_driver else "Add Driver"
    if st.button(btn_label, use_container_width=True):
        if new_d_name and new_d_phone:
            with sqlite3.connect(DB_NAME) as conn:
                if is_editing_driver:
                    conn.execute("UPDATE drivers SET name=?, phone=?, category=? WHERE id=?", 
                                 (new_d_name, new_d_phone, new_d_cat, edit_id))
                    st.toast("Driver updated!", icon="✏️")
                else:
                    conn.execute("INSERT INTO drivers (name, phone, category) VALUES (?, ?, ?)", 
                                 (new_d_name, new_d_phone, new_d_cat))
                    st.toast("Driver added!", icon="✅")
            st.rerun()
        else:
            st.warning("Please fill name and phone.")

@st.dialog("Pickup Details")
def pickup_form_dialog(drivers_df, edit_id=None, data=None):
    if data is None: data = {}
    is_editing = edit_id is not None
    
    # --- Fix Time Reset Issue ---
    # We use a stable time from session state so it doesn't change on every rerun
    if "init_dialog_time" not in st.session_state:
        st.session_state.init_dialog_time = datetime.now().replace(microsecond=0).time()
        
    if is_editing:
        default_date = datetime.strptime(str(data['date']).split(' ')[0], '%Y-%m-%d')
        # If it's an edit, we prefer the existing time, else fallback to the stable init time
        default_time = datetime.strptime(str(data['time']).split('.')[0], '%H:%M:%S').time() if data.get('time') else st.session_state.init_dialog_time
    else:
        default_date = datetime.today()
        default_time = st.session_state.init_dialog_time


    
    driver_list = [f"{r['category']} | {r['name']}" for _, r in drivers_df.iterrows()]
    driver_phones = {f"{r['category']} | {r['name']}": r['phone'] for _, r in drivers_df.iterrows()}
    
    default_driver_idx = 0
    if is_editing:
        for idx, label in enumerate(driver_list):
            if driver_phones[label] == data.get('driver_phone'):
                default_driver_idx = idx
                break

    c1, c2 = st.columns(2)
    with c1:
        # Moved Occupant to top to prevent Date Input from auto-focusing/expanding by default
        u_occupant = st.text_input("Occupant", value=data.get('occupant', ''))
        u_date = st.date_input("Date", value=default_date)
        u_time = st.time_input("Time", value=default_time)

    with c2:
        u_priority = st.selectbox("Priority", ["Low", "Medium", "High", "URGENT"], 
                                 index=["Low", "Medium", "High", "URGENT"].index(data.get('priority', 'Low')))
        u_driver_label = st.selectbox("Driver", options=driver_list, index=default_driver_idx)
        u_destination = st.text_input("Destination", value=data.get('destination', ''))

    u_desc = st.text_area("Notes", value=data.get('description', ''))
    u_include_amount = st.checkbox("Include Amount?", value=bool(data.get('has_amount', False)))
    u_amount = st.text_input("Amount", value=data.get('amount', '')) if u_include_amount else ""

    btn_label = "Update Reminder" if is_editing else "Save Pickup"
    if st.button(btn_label, use_container_width=True):
        with sqlite3.connect(DB_NAME) as conn:
            if is_editing:
                conn.execute('''UPDATE reminders SET date=?, time=?, occupant=?, destination=?, description=?, priority=?, driver_phone=?, has_amount=?, amount=? WHERE id=?''',
                             (str(u_date), str(u_time), u_occupant, u_destination, u_desc, u_priority, driver_phones[u_driver_label], 1 if u_include_amount else 0, u_amount, edit_id))
                st.toast("Reminder updated!", icon="✏️")
            else:
                conn.execute('''INSERT INTO reminders (date, time, occupant, destination, description, priority, driver_phone, has_amount, amount) VALUES (?,?,?,?,?,?,?,?,?)''',
                             (str(u_date), str(u_time), u_occupant, u_destination, u_desc, u_priority, driver_phones[u_driver_label], 1 if u_include_amount else 0, u_amount))
                st.toast("Pickup scheduled!", icon="✅")
        
        # Clear the initial time state so it refreshes next time a dialog opens
        if "init_dialog_time" in st.session_state:
            del st.session_state.init_dialog_time
        st.rerun()


# --- UI LOGIC ---
def reminders_ui():
    init_reminders_db()

    # --- CSS FOR ALL ICONS ---
    icons = {
        "plane":    ui_utils.get_icon_base64("plane"),
        "users":    ui_utils.get_icon_base64("users"),
        "user":     ui_utils.get_icon_base64("user"),
        "plus":     ui_utils.get_icon_base64("plus"),
        "settings": ui_utils.get_icon_base64("settings"),
        "pencil":   ui_utils.get_icon_base64("pencil"),
        "trash":    ui_utils.get_icon_base64("trash"),
        "calendar": ui_utils.get_icon_base64("calendar"),
        "clock":    ui_utils.get_icon_base64("clock"),
        "list":     ui_utils.get_icon_base64("list"),
        "tag":      ui_utils.get_icon_base64("tag"),
        "pin":      ui_utils.get_icon_base64("map-pin"),
        "notes":    ui_utils.get_icon_base64("file-text"),
        "alert":    ui_utils.get_icon_base64("alert-triangle"),
        "wallet":   ui_utils.get_icon_base64("wallet"),
        "save":     ui_utils.get_icon_base64("save"),
        "whatsapp": ui_utils.get_icon_base64("link") # Fallback for WhatsApp
    }

    icon_css = f"""
    <style>
    /* 1. Tabs */
    [data-testid="stTabs"] button:nth-of-type(1) p::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 8px; vertical-align: middle;
        background-color: currentColor; -webkit-mask: url('data:image/svg+xml;base64,{icons["clock"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["clock"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    [data-testid="stTabs"] button:nth-of-type(2) p::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 8px; vertical-align: middle;
        background-color: currentColor; -webkit-mask: url('data:image/svg+xml;base64,{icons["calendar"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["calendar"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}

    /* 2. Action Buttons */
    [data-testid="stPopover"] button p::before {{
        content: ""; display: inline-block; width: 16px; height: 16px; margin-right: 8px; vertical-align: middle;
        background-color: currentColor; -webkit-mask: url('data:image/svg+xml;base64,{icons["settings"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["settings"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    button:has(p:contains("Edit")) p::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: middle;
        background-color: currentColor; -webkit-mask: url('data:image/svg+xml;base64,{icons["pencil"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["pencil"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    button:has(p:contains("Delete")) p::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: middle;
        background-color: #EF4444; -webkit-mask: url('data:image/svg+xml;base64,{icons["trash"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["trash"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    button:has(p:contains("WhatsApp")) p::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: middle;
        background-color: white; -webkit-mask: url('data:image/svg+xml;base64,{icons["whatsapp"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["whatsapp"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}

    /* 3. Form Submit Buttons */
    button:has(p:contains("Add Driver")) p::before,
    button:has(p:contains("Schedule Pickup")) p::before,
    button:has(p:contains("Save Pickup")) p::before {{
        content: ""; display: inline-block; width: 16px; height: 16px; margin-right: 8px; vertical-align: middle;
        background-color: white; -webkit-mask: url('data:image/svg+xml;base64,{icons["plus"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["plus"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    button:has(p:contains("Update")) p::before {{
        content: ""; display: inline-block; width: 16px; height: 16px; margin-right: 8px; vertical-align: middle;
        background-color: white; -webkit-mask: url('data:image/svg+xml;base64,{icons["save"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["save"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}

    /* 4. Input Labels */
    [data-testid="stTextInput"]:has(label:contains("Name")) label::before,
    [data-testid="stTextInput"]:has(label:contains("Occupant")) label::before,
    [data-testid="stSelectbox"]:has(label:contains("Driver")) label::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: middle;
        background-color: #475569; -webkit-mask: url('data:image/svg+xml;base64,{icons["user"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["user"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    [data-testid="stTextInput"]:has(label:contains("Phone")) label::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: middle;
        background-color: #475569; -webkit-mask: url('data:image/svg+xml;base64,{icons["user"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["user"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    [data-testid="stSelectbox"]:has(label:contains("Category")) label::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: middle;
        background-color: #475569; -webkit-mask: url('data:image/svg+xml;base64,{icons["tag"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["tag"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    [data-testid="stDateInput"]:has(label:contains("Date")) label::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: middle;
        background-color: #475569; -webkit-mask: url('data:image/svg+xml;base64,{icons["calendar"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["calendar"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    [data-testid="stTimeInput"]:has(label:contains("Time")) label::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: middle;
        background-color: #475569; -webkit-mask: url('data:image/svg+xml;base64,{icons["clock"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["clock"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    [data-testid="stSelectbox"]:has(label:contains("Priority")) label::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: middle;
        background-color: #475569; -webkit-mask: url('data:image/svg+xml;base64,{icons["alert"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["alert"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    [data-testid="stTextInput"]:has(label:contains("Destination")) label::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: middle;
        background-color: #475569; -webkit-mask: url('data:image/svg+xml;base64,{icons["pin"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["pin"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    [data-testid="stTextArea"]:has(label:contains("Notes")) label::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: middle;
        background-color: #475569; -webkit-mask: url('data:image/svg+xml;base64,{icons["notes"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["notes"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    [data-testid="stTextInput"]:has(label:contains("Amount")) label::before {{
        content: ""; display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: middle;
        background-color: #475569; -webkit-mask: url('data:image/svg+xml;base64,{icons["wallet"]}') no-repeat center; mask: url('data:image/svg+xml;base64,{icons["wallet"]}') no-repeat center; -webkit-mask-size: contain; mask-size: contain;
    }}
    </style>
    """
    st.markdown(icon_css, unsafe_allow_html=True)

    ui_utils.icon_header("Airport & Guest Reminders", "plane")

    # --- SECTION 1 & 2: DRIVER DIRECTORY & SCHEDULE PICKUP ---
    main_col1, main_col2 = st.columns(2)

    with main_col1:
        ui_utils.icon_subheader("Driver Directory", "users")
        if st.button("Add New Driver", use_container_width=True):
            driver_form_dialog()
        
        with st.expander("Current Driver Directory"):
            with sqlite3.connect(DB_NAME) as conn:
                drivers_list_df = pd.read_sql_query("SELECT * FROM drivers ORDER BY category, name ASC", conn)
            
            if not drivers_list_df.empty:
                for _, d_row in drivers_list_df.iterrows():
                    dr_col1, dr_opt = st.columns([5, 1])
                    dr_col1.write(f"**{d_row['category']}** | {d_row['name']} ({d_row['phone']})")
                    with dr_opt:
                        with st.popover("Options"):
                            if st.button("Edit", key=f"edit_dr_{d_row['id']}", use_container_width=True):
                                driver_form_dialog(d_row['id'], d_row.to_dict())
                            if st.button("Delete", key=f"del_dr_{d_row['id']}", use_container_width=True):
                                with sqlite3.connect(DB_NAME) as conn:
                                    conn.execute("DELETE FROM drivers WHERE id=?", (d_row['id'],))
                                st.rerun()
            else:
                st.info("No drivers in directory.")

    with main_col2:
        ui_utils.icon_subheader("Schedule a Pickup", "plus")
        with sqlite3.connect(DB_NAME) as conn:
            drivers_df = pd.read_sql_query("SELECT * FROM drivers ORDER BY category, name ASC", conn)
        
        if not drivers_df.empty:
            if st.button("Schedule Pickup", type="primary", use_container_width=True):
                st.session_state.init_dialog_time = datetime.now().replace(microsecond=0).time()
                pickup_form_dialog(drivers_df=drivers_df)

        else:
            st.warning("Add a driver in the directory above first.")

    st.divider()

    # --- SECTION 3: BROWSE & SORT SCHEDULE ---
    ui_utils.icon_subheader("Schedule Explorer", "calendar")
    
    with sqlite3.connect(DB_NAME) as conn:
        full_df = pd.read_sql_query("SELECT * FROM reminders", conn)
    
    if not full_df.empty:
        full_df['dt_obj'] = pd.to_datetime(full_df['date'] + ' ' + full_df['time'])
        now = datetime.now()

        f1, f2, f3 = st.columns([2, 2, 1])
        with f1:
            # Wrap in expander to prevent the date filter from 'starting expanded' or taking up space by default
            with st.expander("Filter by Specific Date", expanded=False):
                date_search = st.date_input("Select Date", value=None)

        with f2:
            sort_order = st.selectbox("Sort By Time", ["Soonest First", "Latest First"])
        with f3:
            if st.button("Clear Filter"):
                st.rerun()

        if date_search:
            full_df = full_df[full_df['date'] == str(date_search)]

        upcoming_df = full_df[full_df['dt_obj'] >= now].sort_values(by='dt_obj', ascending=(sort_order == "Soonest First"))
        past_df = full_df[full_df['dt_obj'] < now].sort_values(by='dt_obj', ascending=False)

        tab1, tab2 = st.tabs([f"Upcoming ({len(upcoming_df)})", f"Past Schedules ({len(past_df)})"])

        with tab1:
            display_schedule(upcoming_df)
        with tab2:
            display_schedule(past_df, is_past=True)
    else:
        st.info("No pickups found.")

def display_schedule(df, is_past=False):
    if df.empty:
        st.caption("No records to show.")
        return

    for _, row in df.iterrows():
        with st.container():
            c1, c2, c3 = st.columns([1, 2.5, 1.5])
            
            cal_icon = ui_utils.render_icon("calendar", color="#666", size=13, margin="0 4px 0 0")
            clock_icon = ui_utils.render_icon("clock", color="#666", size=13, margin="0 4px 0 0")
            user_icon = ui_utils.render_icon("user", color="#1565C0", size=15, margin="0 8px 0 0")
            pin_icon = ui_utils.render_icon("map-pin", color="#666", size=13, margin="0 4px 0 0")
            
            with c1:
                st.markdown(f'<div style="display:flex;align-items:center;font-weight:bold;font-size:0.9em;">{cal_icon}{row["date"]}</div>', unsafe_allow_html=True)
                st.markdown(f'<div style="display:flex;align-items:center;color:grey;font-size:0.85em;">{clock_icon}{row["time"]}</div>', unsafe_allow_html=True)
            with c2:
                p_colors = {"Low": "#22C55E", "Medium": "#EAB308", "High": "#F97316", "URGENT": "#EF4444"}
                p_color = p_colors.get(row['priority'], "grey")
                priority_dot = f'<span style="height:10px;width:10px;background-color:{p_color};border-radius:50%;display:inline-block;margin-right:8px;"></span>'
                
                st.markdown(f'<div style="display:flex;align-items:center;font-weight:bold;">{priority_dot}{user_icon}{row["occupant"]}</div>', unsafe_allow_html=True)
                st.markdown(f'<div style="display:flex;align-items:center;font-size:0.9em;color:#444;margin-top:4px;">{pin_icon} {row["destination"]}</div>', unsafe_allow_html=True)
                if is_past:
                    st.caption("Task Completed")
            with c3:
                # Clean phone number (strip spaces, +, etc.) for the WhatsApp URL
                clean_phone = "".join(filter(str.isdigit, str(row['driver_phone'])))
                
                # Construct a comprehensive message
                msg_body = (
                    f"PICKUP ALERT\n"
                    f"Occupant: {row['occupant']}\n"
                    f"Destination: {row['destination']}\n"
                    f"Date: {row['date']}\n"
                    f"Time: {row['time']}\n"
                    f"Priority: {row['priority']}"
                )
                if row.get('description'):
                    msg_body += f"\nNotes: {row['description']}"
                if row.get('has_amount') and row.get('amount'):
                    msg_body += f"\nAmount: ₦{row['amount']}"
                
                msg = urllib.parse.quote(msg_body)
                # Using api.whatsapp.com often bypasses the 'select contact' screen better than wa.me on some platforms
                whatsapp_url = f"https://api.whatsapp.com/send?phone={clean_phone}&text={msg}"
                st.link_button("WhatsApp", whatsapp_url, use_container_width=True)
                
                sc1, sc2 = st.columns(2)
                if sc1.button("Edit", key=f"ed_{row['id']}", use_container_width=True):
                    with sqlite3.connect(DB_NAME) as conn:
                        drivers_df = pd.read_sql_query("SELECT * FROM drivers ORDER BY category, name ASC", conn)
                    st.session_state.init_dialog_time = datetime.now().replace(microsecond=0).time()
                    pickup_form_dialog(drivers_df=drivers_df, edit_id=row['id'], data=row.to_dict())

                if sc2.button("Delete", key=f"dl_{row['id']}", use_container_width=True):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("DELETE FROM reminders WHERE id = ?", (row['id'],))
                    st.rerun()
            st.divider()