from streamlit import header
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import ui_utils
import plotly.express as px
import re

DB_NAME = 'alpr_data.db'

# --- DATABASE LOGIC ---
def init_expense_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS expenses 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, 
             date TEXT, 
             category TEXT, 
             item TEXT, 
             amount REAL, 
             description TEXT, 
             logged_by TEXT,
             vehicle_id TEXT)''')
        conn.commit()

@st.dialog("Delete Record")
def delete_record_dialog():
    del_id = st.number_input("Enter ID to Delete", min_value=1, step=1)
    if st.button("Confirm Delete", use_container_width=True):
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("DELETE FROM expenses WHERE id = ?", (del_id,))
        st.toast("Record deleted successfully!", icon="🗑️")
        st.rerun()

# --- UI LOGIC ---
def expense_ui():
    init_expense_db()
    ui_utils.icon_header("Expense & Fuel Logger", "wallet")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Log Expense", "Transaction History", "Financial Summary", "📊 Excel Report Importer"])

    # --- TAB 1: LOG EXPENSE ---
    with tab1:
        ui_utils.icon_subheader("Add New Expenditure", "plus")
        with st.form("expense_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                category = st.selectbox("Category", ["Fuel", "Vehicle Maintenance", "Staff Welfare", "Office Supplies", "Utility", "Other"])
                item = st.text_input("Item / Purpose", placeholder="e.g. Petrol for Van 1")
                amount = st.number_input("Amount (NGN)", min_value=0.0, step=0.01)
            
            with col2:
                # If Fuel or Vehicle Maintenance, allow linking to a vehicle
                vehicle_id = st.text_input("Vehicle ID (Optional)", placeholder="e.g. Plate # or Fleet ID")
                date = st.date_input("Transaction Date", value=datetime.today())
                logged_by = st.text_input("Logged By", value=st.session_state.get("username", ""))

            description = st.text_area("Additional Details")

            if st.form_submit_button("Submit Expense"):
                if item and amount > 0:
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute('''INSERT INTO expenses (date, category, item, amount, description, logged_by, vehicle_id) 
                                        VALUES (?, ?, ?, ?, ?, ?, ?)''', 
                                     (str(date), category, item, amount, description, logged_by, vehicle_id))
                    st.success(f"Successfully logged ₦{amount} for {item}")
                    st.rerun()
                else:
                    st.error("Please provide the Item name and an Amount greater than 0.")

    # --- TAB 2: TRANSACTION HISTORY ---
    with tab2:
        ui_utils.icon_subheader("Recent Expenses", "list")
        with sqlite3.connect(DB_NAME) as conn:
            df = pd.read_sql_query("SELECT * FROM expenses ORDER BY date DESC", conn)
        
        if not df.empty:
            # Filter by category
            filter_cat = st.multiselect("Filter by Category", options=df['category'].unique(), default=df['category'].unique())
            filtered_df = df[df['category'].isin(filter_cat)]
            
            st.dataframe(filtered_df, use_container_width=True, hide_index=True)
            
            # Admin delete capability
            if st.session_state.get("role") == "admin":
                if st.button("Delete Record", use_container_width=True):
                    delete_record_dialog()
        else:
            st.info("No expenses recorded yet.")

    # --- TAB 3: FINANCIAL SUMMARY ---
    with tab3:
        ui_utils.icon_subheader("Expense Breakdown", "bar-chart")
        if not df.empty:
            # Pie Chart: Spending by Category
            fig_pie = px.pie(df, values='amount', names='category', title="Spending by Category", hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)

            # Bar Chart: Spending Over Time
            df['date'] = pd.to_datetime(df['date'])
            time_df = df.groupby('date')['amount'].sum().reset_index()
            fig_line = px.bar(time_df, x='date', y='amount', title="Daily Spending Trend", labels={'amount': 'Total Spent (₦)'})
            st.plotly_chart(fig_line, use_container_width=True)
            
            # Total Stats
            total_spent = df['amount'].sum()
            st.metric("Total Period Expenditure", f"₦{total_spent:,.2f}")
        else:
            st.info("Insufficient data for analytics.")

    # --- NEW TAB 4: EXCEL REPORT IMPORTER ---
    with tab4:
        st.subheader("📬 Import Daily Mileage from Tracksolid Email Report")
        st.markdown("Download the daily Excel file from your email and drop it here to update vehicle distances instantly.")

        uploaded_file = st.file_uploader("Choose Tracksolid Report File", type=["xls", "xlsx"])

        if uploaded_file is not None:
            try:
                # 1. Read the file. We try 'xlrd' engine for older .xls sheets automatically
                engine_choice = 'xlrd' if uploaded_file.name.endswith('.xls') else 'openpyxl'
                df_excel = pd.read_excel(uploaded_file, engine=engine_choice, header = 1)

                st.write("### 🔍 Previewing Uploaded Report Data:")
                st.dataframe(df_excel.head(5), use_container_width=True)

                # 2. Dynamic Column Matching 
                # Vendor reports often change layouts, so we search for columns containing key phrases
                plate_col = None
                km_col = None

                for col in df_excel.columns:
                    col_clean = str(col).strip().lower()
                    if 'device' in col_clean:
                        plate_col = col
                    if 'mileage' in col_clean:
                        km_col = col

                if plate_col and km_col:
                    st.success(f"Found Data Alignment! Mapping column **'{plate_col}'** to Plates and **'{km_col}'** to Distance.")
                    
                    if st.button("🚀 Process & Sync Odometer Logs", type="primary"):
                        success_count = 0
                        
                        with sqlite3.connect(DB_NAME) as conn:
                            for _, row in df_excel.dropna(subset=[plate_col, km_col]).iterrows():
                                # Clean the plate string (remove spaces/dashes)
                                raw_plate = str(row[plate_col]).upper().strip()
                                clean_plate = re.sub(r'[^A-Z0-9]', '', raw_plate)
                                
                                try:
                                    total_km = float(row[km_col])
                                except ValueError:
                                    continue # Skip if row contains header text like "km" instead of a number

                                # Log this directly into your system as a background metadata note
                                # We record it with $0 cost since it's an automated status sync, not an active fuel purchase
                                note = f"[Odometer Auto-Sync via Email Report: {total_km} km]"
                                
                                conn.execute('''
                                    INSERT INTO expenses (date, category, item, amount, description, logged_by, vehicle_id) 
                                    VALUES (?, 'Vehicle Maintenance', 'Mileage Auto-Sync', 0.0, ?, 'AI Importer', ?)
                                ''', (datetime.now().strftime("%Y-%m-%d"), note, clean_plate))
                                success_count += 1
                        
                        st.balloons()
                        st.success(f"Successfully sync-logged {success_count} vehicles into the database!")
                else:
                    st.error("Could not find obvious columns for 'Plate Number' and 'Total KM' in this sheet. Please verify the file structure.")
                    st.info(f"Detected headers in your file: {list(df_excel.columns)}")

            except Exception as e:
                st.error(f"Error parsing the file layout: {str(e)}")