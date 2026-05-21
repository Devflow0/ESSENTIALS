import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import datetime
import ui_utils

DB_NAME = 'alpr_data.db'

# ─────────────────────────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────────────────────────
def init_vehicle_tracker_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS vehicle_trips (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                date          TEXT    NOT NULL,
                plate         TEXT    NOT NULL,
                driver        TEXT    DEFAULT '',
                route         TEXT    DEFAULT '',
                distance_km   REAL    NOT NULL DEFAULT 0,
                fuel_litres   REAL    NOT NULL DEFAULT 0,
                fuel_cost_ngn REAL    NOT NULL DEFAULT 0,
                notes         TEXT    DEFAULT '',
                logged_by     TEXT    DEFAULT ''
            )
        ''')
        conn.commit()


def get_trips():
    with sqlite3.connect(DB_NAME) as conn:
        df = pd.read_sql_query(
            "SELECT * FROM vehicle_trips ORDER BY date DESC, id DESC", conn
        )
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
    return df


# ─────────────────────────────────────────────────────────────────
# MAIN UI
# ─────────────────────────────────────────────────────────────────
def vehicle_tracker_ui():
    init_vehicle_tracker_db()
    ui_utils.icon_header("Vehicle Distance & Fuel Tracker", "truck")

    df = get_trips()

    # ── KPI Row ───────────────────────────────────────────────────
    ui_utils.icon_subheader("Fleet Overview", "bar-chart-2")
    k1, k2, k3, k4 = st.columns(4)

    if not df.empty:
        k1.metric("Total Trips", len(df))
        k2.metric("Total Distance", f"{df['distance_km'].sum():,.1f} km")
        k3.metric("Total Fuel Cost", f"₦{df['fuel_cost_ngn'].sum():,.2f}")
        k4.metric("Unique Vehicles", df['plate'].nunique())
    else:
        for col in [k1, k2, k3, k4]:
            col.metric("—", "0")

    st.divider()

    # ── Charts (only if data exists) ──────────────────────────────
    if not df.empty:
        ch1, ch2 = st.columns(2)

        with ch1:
            ui_utils.icon_subheader("Distance by Vehicle", "activity")
            dist_by_plate = (
                df.groupby('plate')['distance_km']
                .sum()
                .reset_index()
                .sort_values('distance_km', ascending=True)
            )
            fig_dist = px.bar(
                dist_by_plate, x='distance_km', y='plate', orientation='h',
                labels={'distance_km': 'km', 'plate': 'Vehicle'},
                template='plotly_white', color_discrete_sequence=['#3366ff']
            )
            fig_dist.update_layout(yaxis={'categoryorder': 'total ascending'})
            st.plotly_chart(fig_dist, use_container_width=True, key="vt_dist_chart")

        with ch2:
            ui_utils.icon_subheader("Fuel Cost by Vehicle", "zap")
            cost_by_plate = (
                df.groupby('plate')['fuel_cost_ngn']
                .sum()
                .reset_index()
                .sort_values('fuel_cost_ngn', ascending=False)
            )
            fig_cost = px.pie(
                cost_by_plate, names='plate', values='fuel_cost_ngn',
                hole=0.42, template='plotly_white',
                labels={'fuel_cost_ngn': '₦', 'plate': 'Vehicle'}
            )
            st.plotly_chart(fig_cost, use_container_width=True, key="vt_cost_chart")

        # Trend line
        ui_utils.icon_subheader("Distance Trend Over Time", "trending-up")
        trend = df.groupby('date')['distance_km'].sum().reset_index()
        fig_trend = px.line(
            trend, x='date', y='distance_km', markers=True,
            labels={'distance_km': 'km', 'date': 'Date'},
            template='plotly_white', color_discrete_sequence=['#00CC96']
        )
        st.plotly_chart(fig_trend, use_container_width=True, key="vt_trend_chart")

    st.divider()

    # ── Tabs: Log Trip | Per-Vehicle Report | History ─────────────
    tab_log, tab_report, tab_history = st.tabs([
        "📋 Log Trip", "🚗 Per-Vehicle Report", "🗂 Full History"
    ])

    # ── TAB 1: Log a new trip ─────────────────────────────────────
    with tab_log:
        with st.form("vt_log_form", clear_on_submit=True):
            r1c1, r1c2, r1c3 = st.columns(3)
            plate      = r1c1.text_input("Vehicle Plate").upper().strip()
            driver     = r1c2.text_input("Driver Name")
            trip_date  = r1c3.date_input("Trip Date", value=datetime.today())

            r2c1, r2c2, r2c3 = st.columns(3)
            distance   = r2c1.number_input("Distance (km)", min_value=0.0, step=0.1)
            fuel_l     = r2c2.number_input("Fuel Used (litres)", min_value=0.0, step=0.1)
            fuel_cost  = r2c3.number_input("Fuel Cost (₦)", min_value=0.0, step=50.0)

            route = st.text_input("Route / Destination", placeholder="e.g. Lagos → Ibadan")
            notes = st.text_area("Notes", height=70, placeholder="Optional notes about the trip")

            if st.form_submit_button("Save Trip Log", use_container_width=True):
                if plate and distance > 0:
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute('''
                            INSERT INTO vehicle_trips
                                (date, plate, driver, route, distance_km,
                                 fuel_litres, fuel_cost_ngn, notes, logged_by)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            str(trip_date), plate, driver, route,
                            distance, fuel_l, fuel_cost, notes,
                            st.session_state.get("username", "Staff")
                        ))
                    st.toast(f"Trip logged for {plate}!", icon="✅")
                    st.rerun()
                else:
                    st.warning("Plate number and distance (km) are required.")

    # ── TAB 2: Per-vehicle report ─────────────────────────────────
    with tab_report:
        if df.empty:
            st.info("No trips logged yet.")
        else:
            plates = sorted(df['plate'].unique().tolist())
            sel_plate = st.selectbox("Select Vehicle", options=plates, key="vt_report_plate")

            vdf = df[df['plate'] == sel_plate].copy()

            vm1, vm2, vm3, vm4 = st.columns(4)
            vm1.metric("Trips", len(vdf))
            vm2.metric("Total Distance", f"{vdf['distance_km'].sum():,.1f} km")
            vm3.metric("Fuel Used", f"{vdf['fuel_litres'].sum():,.1f} L")
            vm4.metric("Fuel Spend", f"₦{vdf['fuel_cost_ngn'].sum():,.2f}")

            if len(vdf) > 1:
                avg_eff = vdf['distance_km'].sum() / vdf['fuel_litres'].sum() \
                    if vdf['fuel_litres'].sum() > 0 else 0
                st.caption(f"Average fuel efficiency: **{avg_eff:.1f} km/L**")

            st.dataframe(
                vdf[['date', 'driver', 'route', 'distance_km', 'fuel_litres',
                      'fuel_cost_ngn', 'notes']]
                .rename(columns={
                    'date': 'Date', 'driver': 'Driver', 'route': 'Route',
                    'distance_km': 'km', 'fuel_litres': 'Litres',
                    'fuel_cost_ngn': 'Fuel Cost (₦)', 'notes': 'Notes'
                }),
                use_container_width=True, hide_index=True
            )

    # ── TAB 3: Full history + admin delete ───────────────────────
    with tab_history:
        if df.empty:
            st.info("No trip history yet.")
        else:
            st.dataframe(
                df[['date', 'plate', 'driver', 'route', 'distance_km',
                     'fuel_litres', 'fuel_cost_ngn', 'notes', 'logged_by']]
                .rename(columns={
                    'date': 'Date', 'plate': 'Plate', 'driver': 'Driver',
                    'route': 'Route', 'distance_km': 'km',
                    'fuel_litres': 'Litres', 'fuel_cost_ngn': 'Fuel Cost (₦)',
                    'notes': 'Notes', 'logged_by': 'Logged By'
                }),
                use_container_width=True, hide_index=True
            )

            if st.session_state.get("role") == "admin":
                st.divider()
                if st.button("🗑 Clear All Trip Logs", type="secondary"):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("DELETE FROM vehicle_trips")
                    st.toast("All trip logs cleared.", icon="🗑")
                    st.rerun()
