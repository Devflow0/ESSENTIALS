import streamlit as st
import cv2
import sqlite3
import pandas as pd
import requests
from datetime import datetime, timedelta
import ui_utils
from db_security import decrypt_data, decrypt_bytes, encrypt_data
import os
import socket
import numpy as np

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        s.connect(('8.8.8.8', 1))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "localhost"
    return local_ip

DB_NAME = 'alpr_data.db'
SERVER_IP = get_local_ip()
SERVER_URL = f"http://{SERVER_IP}:8000"

# ── Asset directories ─────────────────────────────────────────────────
MODELS_DIR = os.path.join("assets", "Models")

def init_face_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS face_movements
            (id INTEGER PRIMARY KEY AUTOINCREMENT, face_id INTEGER, event TEXT,
             timestamp DATETIME, name TEXT, snapshot_path TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS face_watchlist
            (name TEXT PRIMARY KEY, reason TEXT, added_on DATETIME)''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS face_profiles (
                name                TEXT PRIMARY KEY,
                embedding           BLOB,
                first_seen          DATETIME,
                last_seen           DATETIME,
                total_visits        INTEGER DEFAULT 0,
                notes               TEXT DEFAULT '',
                last_snapshot_path  TEXT DEFAULT '',
                face_id             INTEGER
            )
        ''')
        # ── Migration: add face_id column to existing databases ──────────────
        try:
            conn.execute("ALTER TABLE face_profiles ADD COLUMN face_id INTEGER")
        except sqlite3.OperationalError:
            pass  # Column already exists
        # Back-fill face_id from rowid for any profiles that lack one
        conn.execute("UPDATE face_profiles SET face_id = rowid WHERE face_id IS NULL")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_face_profiles_face_id "
            "ON face_profiles(face_id)"
        )
        conn.commit()

def get_decrypted_image(path):
    if path and os.path.exists(path):
        try:
            with open(path, 'rb') as f:
                encrypted_bytes = f.read()
            return decrypt_bytes(encrypted_bytes)
        except:
            return None
    return None

def get_analytics_data():
    with sqlite3.connect(DB_NAME) as conn:
        df = pd.read_sql_query("SELECT * FROM face_movements", conn)

    if not df.empty:
        df['name'] = df['name'].apply(decrypt_data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['date'] = df['timestamp'].dt.date
    return df

# ─────────────────────────────────────────────────────────────────────────────
# Helper: load all face embeddings from DB for similarity computation
# ─────────────────────────────────────────────────────────────────────────────
def _load_all_embeddings():
    """Returns a dict of {name: (face_id, np.ndarray embedding)}."""
    embeddings = {}
    with sqlite3.connect(DB_NAME) as conn:
        rows = conn.execute(
            "SELECT name, face_id, embedding FROM face_profiles WHERE embedding IS NOT NULL"
        ).fetchall()
    for name, face_id, blob in rows:
        feature = np.frombuffer(blob, dtype=np.float32).reshape(1, 128)
        embeddings[name] = (face_id, feature)
    return embeddings

def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two (1,128) embeddings."""
    a_flat = a.flatten()
    b_flat = b.flatten()
    denom = (np.linalg.norm(a_flat) * np.linalg.norm(b_flat))
    if denom == 0:
        return 0.0
    return float(np.dot(a_flat, b_flat) / denom)

# ─────────────────────────────────────────────────────────────────────────────
# Back-Search Engine
# ─────────────────────────────────────────────────────────────────────────────
def back_search_face_history(name: str, face_id: int, embedding_blob: bytes,
                              progress_bar=None) -> dict:
    """
    Scan all face_movements rows that have face_id=0 (unknown / legacy) and a
    valid snapshot.  For each snapshot, decrypt the image, detect faces, compute
    the SFace embedding, and compare against the target embedding.

    Any row whose best cosine score >= 0.363 (the live recognition threshold)
    is retroactively updated with the correct face_id and encrypted name.

    Returns: {scanned: int, matched: int, updated: int} or adds 'error' key.
    """
    try:
        detector  = cv2.FaceDetectorYN.create(
            os.path.join(MODELS_DIR, "face_detection_yunet.onnx"), "", (320, 320)
        )
        recognizer = cv2.FaceRecognizerSF.create(
            os.path.join(MODELS_DIR, "face_recognition_sface.onnx"), ""
        )
    except Exception as exc:
        return {"scanned": 0, "matched": 0, "updated": 0, "error": str(exc)}

    target_emb  = np.frombuffer(embedding_blob, dtype=np.float32).reshape(1, 128)
    secure_name = encrypt_data(name)

    # Only look at rows not yet attributed to ANY known person (face_id = 0 / NULL)
    with sqlite3.connect(DB_NAME) as conn:
        candidates = pd.read_sql_query(
            """
            SELECT id, snapshot_path
            FROM   face_movements
            WHERE  (face_id = 0 OR face_id IS NULL)
              AND  snapshot_path IS NOT NULL
              AND  snapshot_path != ''
            ORDER BY id DESC
            """,
            conn
        )

    total   = len(candidates)
    scanned = 0
    matched = 0
    updated = 0

    for _, row in candidates.iterrows():
        scanned += 1
        if progress_bar is not None:
            pct  = scanned / max(total, 1)
            progress_bar.progress(
                pct, text=f"Scanning record {scanned} of {total}…"
            )

        # ── Decrypt snapshot ─────────────────────────────────────────────────
        img_bytes = get_decrypted_image(row['snapshot_path'])
        if img_bytes is None:
            continue

        try:
            nparr = np.frombuffer(img_bytes, dtype=np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except Exception:
            continue

        if frame is None:
            continue

        # ── Detect faces ─────────────────────────────────────────────────────
        h, w = frame.shape[:2]
        try:
            detector.setInputSize((w, h))
            _, faces = detector.detect(frame)
        except Exception:
            continue

        if faces is None:
            continue

        # ── Match against target embedding ────────────────────────────────────
        best_score = 0.0
        for face in faces:
            box = list(map(int, face[:4]))
            # Skip out-of-bounds detections
            if box[0] < 0 or box[1] < 0 or box[0]+box[2] > w or box[1]+box[3] > h:
                continue
            try:
                face_align = recognizer.alignCrop(frame, face)
                feat       = recognizer.feature(face_align)
                score      = recognizer.match(
                    feat, target_emb, cv2.FaceRecognizerSF_FR_COSINE
                )
                if score > best_score:
                    best_score = score
            except Exception:
                continue

        if best_score >= 0.363:
            matched += 1
            try:
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute(
                        "UPDATE face_movements SET face_id = ?, name = ? WHERE id = ?",
                        (face_id, secure_name, int(row['id']))
                    )
                updated += 1
            except Exception:
                pass

    if progress_bar is not None:
        progress_bar.progress(
            1.0, text=f"Done — scanned {scanned}, matched {matched}."
        )

    return {"scanned": scanned, "matched": matched, "updated": updated}

# ─────────────────────────────────────────────────────────────────────────────
# Fragment: Face Intelligence (profiles + history + similar faces)
# ─────────────────────────────────────────────────────────────────────────────
@st.fragment(run_every=8.0)
def face_intel_fragment():
    # ── Load profiles ─────────────────────────────────────────────────────────
    with sqlite3.connect(DB_NAME) as conn:
        profiles = pd.read_sql_query(
            "SELECT face_id, name, first_seen, last_seen, total_visits "
            "FROM face_profiles ORDER BY last_seen DESC",
            conn
        )

    if profiles.empty:
        st.info("No known faces registered. Use the Register Person button to add some.")
        return

    # ── Compact toolbar: name search + back-search button on one row ──────────
    tc1, tc2 = st.columns([3, 1])
    with tc1:
        name_search = st.text_input(
            "Search", key="face_search",
            placeholder="🔍  Search by name…",
            label_visibility="collapsed"
        ).upper().strip()
    with tc2:
        run_bs_now = st.button(
            "🔎 Back-Search", key="btn_bs_toolbar",
            use_container_width=True,
            help="Re-scan unattributed snapshots for the selected person"
        )

    filtered = profiles.copy()
    if name_search:
        filtered = filtered[
            filtered['name'].str.upper().str.contains(name_search, na=False)
        ]
    st.caption(f"{len(filtered)} of {len(profiles)} person(s)")

    # ── Two-column layout ─────────────────────────────────────────────────────
    left, right = st.columns([2, 3])

    # ── LEFT: profiles table ──────────────────────────────────────────────────
    with left:
        sel = st.dataframe(
            filtered.rename(columns={
                "face_id": "ID", "name": "Name",
                "last_seen": "Last Seen", "total_visits": "Visits"
            })[["ID", "Name", "Last Seen", "Visits"]],
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="face_profile_table",
            height=280
        )

    # ── Resolve selection ─────────────────────────────────────────────────────
    selected_name    = None
    selected_face_id = None

    if sel and sel.selection.rows and not filtered.empty and sel.selection.rows[0] < len(filtered):
        _rd = filtered.iloc[sel.selection.rows[0]]
        selected_name, selected_face_id = _rd['name'], _rd['face_id']
    elif len(filtered) == 1:
        selected_name, selected_face_id = filtered.iloc[0]['name'], filtered.iloc[0]['face_id']

    # Safe int coercion (pandas nullable ints come back as float64 when NULLs exist)
    if selected_name:
        try:
            selected_face_id = (
                int(selected_face_id)
                if selected_face_id is not None and str(selected_face_id) != 'nan'
                else None
            )
        except (ValueError, TypeError):
            selected_face_id = None

    # ── RIGHT: detail panel ───────────────────────────────────────────────────
    with right:
        if not selected_name:
            st.info("← Select a person to view their history.")
        else:
            face_id_label = f"#{selected_face_id}" if selected_face_id is not None else "—"

            _pm = profiles[profiles['name'] == selected_name]
            if _pm.empty:
                st.warning("Profile refreshing — please re-select.")
            else:
                vrow = _pm.iloc[0]
                # Compact header: name + ID + delete button on one row
                hc1, hc2 = st.columns([4, 1])
                with hc1:
                    st.markdown(f"**{selected_name}**  `ID {face_id_label}`")
                with hc2:
                    if st.button("🗑️", key="btn_del_face",
                                 help=f"Delete {selected_name}"):
                        st.session_state["_del_target"] = (
                            selected_name, selected_face_id
                        )
                        delete_face_dialog(selected_name, selected_face_id)
                mc1, mc2, mc3 = st.columns(3)
                mc1.metric("Visits", int(vrow['total_visits'] or 0))
                mc2.metric("First seen", str(vrow['first_seen'])[:10] if vrow['first_seen'] else "—")
                mc3.metric("Last seen",  str(vrow['last_seen'])[:10]  if vrow['last_seen']  else "—")

            # ── Movement history ──────────────────────────────────────────────
            with sqlite3.connect(DB_NAME) as conn:
                if selected_face_id is not None:
                    raw_moves = pd.read_sql_query(
                        "SELECT event, timestamp, snapshot_path FROM face_movements "
                        "WHERE face_id = ? ORDER BY id DESC",
                        conn, params=(selected_face_id,)
                    )
                else:
                    raw_moves = pd.read_sql_query(
                        "SELECT event, timestamp, snapshot_path, name FROM face_movements "
                        "WHERE face_id = 0 ORDER BY id DESC",
                        conn
                    )
                    if not raw_moves.empty:
                        raw_moves['name_dec'] = raw_moves['name'].apply(decrypt_data)
                        raw_moves = raw_moves[raw_moves['name_dec'] == selected_name][
                            ['event', 'timestamp', 'snapshot_path']
                        ].copy()

            if not raw_moves.empty:
                raw_moves['timestamp'] = pd.to_datetime(raw_moves['timestamp'])
                history = raw_moves.sort_values('timestamp', ascending=False)

                # History table + snapshot side-by-side when room allows
                ht1, ht2 = st.columns([3, 2])
                with ht1:
                    log_sel = st.dataframe(
                        history.rename(columns={"timestamp": "Time", "event": "Event"})[
                            ["Time", "Event"]
                        ],
                        use_container_width=True,
                        hide_index=True,
                        on_select="rerun",
                        selection_mode="single-row",
                        key="face_history_table",
                        height=160
                    )
                with ht2:
                    snap_path = None
                    if log_sel and log_sel.selection.rows:
                        row_idx = log_sel.selection.rows[0]
                        if row_idx < len(history):
                            snap_path = history.iloc[row_idx]['snapshot_path']
                    if not snap_path:
                        with sqlite3.connect(DB_NAME) as conn:
                            _r = conn.execute(
                                "SELECT last_snapshot_path FROM face_profiles WHERE name=?",
                                (selected_name,)
                            ).fetchone()
                        snap_path = _r[0] if _r else None
                    if snap_path:
                        img = get_decrypted_image(snap_path)
                        if img:
                            st.image(img, use_container_width=True)
            else:
                st.caption("No movement history yet.")

            # ── Back-Search (triggered from toolbar button) ───────────────────
            if run_bs_now:
                with sqlite3.connect(DB_NAME) as _conn:
                    _emb_row = _conn.execute(
                        "SELECT embedding FROM face_profiles WHERE name = ?",
                        (selected_name,)
                    ).fetchone()
                if _emb_row is None or _emb_row[0] is None:
                    st.warning("No embedding — re-register this person with an image first.")
                elif selected_face_id is None:
                    st.warning("Face ID not assigned — re-register to fix.")
                else:
                    with sqlite3.connect(DB_NAME) as _conn:
                        _cand = _conn.execute(
                            "SELECT COUNT(*) FROM face_movements "
                            "WHERE (face_id=0 OR face_id IS NULL) "
                            "AND snapshot_path IS NOT NULL AND snapshot_path!=''"
                        ).fetchone()[0]
                    if _cand == 0:
                        st.info("No unattributed records to scan.")
                    else:
                        _prog = st.progress(0, text="Back-searching…")
                        _res  = back_search_face_history(
                            selected_name, selected_face_id, _emb_row[0], _prog
                        )
                        _prog.empty()
                        if "error" in _res:
                            st.error(_res["error"])
                        elif _res["matched"] > 0:
                            st.success(
                                f"✅ {_res['matched']} match(es) found in "
                                f"{_res['scanned']} records and linked to **{selected_name}**."
                            )
                        else:
                            st.info(f"Scanned {_res['scanned']} records — no matches found.")

    # ── Similar Faces: compact inline section ─────────────────────────────────
    if selected_name and selected_face_id is not None:
        with st.expander("🔍 Similar Faces", expanded=False):
            sf1, sf2 = st.columns([2, 1])
            with sf1:
                st.caption("Other profiles close in embedding space — potential duplicates.")
            with sf2:
                sim_threshold = st.slider(
                    "Threshold", 0.10, 0.50, 0.30, 0.01,
                    key="sim_threshold_slider",
                    help="0.363+ = live recognition match"
                )

            all_emb = _load_all_embeddings()
            t_entry = all_emb.get(selected_name)
            if t_entry is None:
                st.caption("No embedding stored for this person.")
            else:
                _, t_emb = t_entry
                similar = [
                    {
                        "ID":   f"#{oid}" if oid else "—",
                        "Name": oname,
                        "Sim":  round(_cosine_similarity(t_emb, oemb), 3),
                        "⚠️":   "Yes" if _cosine_similarity(t_emb, oemb) >= 0.363 else ""
                    }
                    for oname, (oid, oemb) in all_emb.items()
                    if oname != selected_name
                    and _cosine_similarity(t_emb, oemb) >= sim_threshold
                ]
                if similar:
                    sim_df = pd.DataFrame(similar).sort_values("Sim", ascending=False)
                    st.dataframe(sim_df, use_container_width=True, hide_index=True, height=160)
                    if any(r["⚠️"] for r in similar):
                        st.warning("Some matches exceed the recognition threshold — possible duplicates.")
                else:
                    st.caption(f"No matches above {sim_threshold:.2f} — unique identity.")

# ─────────────────────────────────────────────────────────────────────────────
# Dialog: Delete Face
# ─────────────────────────────────────────────────────────────────────────────
@st.dialog("🗑️ Delete Face Profile", width="small")
def delete_face_dialog(name: str, face_id: int):
    """Two-step confirmation before deleting a face profile + its movements."""
    st.warning(f"You are about to permanently delete **{name}** (ID #{face_id}).")
    also_movements = st.checkbox(
        "Also delete all movement history for this person",
        value=True,
        help="Removes face_movements rows linked to this Face ID"
    )
    st.caption("⚠️ This action cannot be undone.")

    dc1, dc2 = st.columns(2)
    with dc1:
        if st.button("🗑️ Confirm Delete", type="primary", use_container_width=True,
                     key="btn_confirm_del"):
            try:
                with sqlite3.connect(DB_NAME) as conn:
                    if also_movements:
                        conn.execute(
                            "DELETE FROM face_movements WHERE face_id = ?", (face_id,)
                        )
                    conn.execute(
                        "DELETE FROM face_profiles WHERE name = ?", (name,)
                    )
                    conn.execute(
                        "DELETE FROM face_watchlist WHERE name = ?", (name,)
                    )
                # Tell vision server to reload profiles
                try:
                    requests.post(f"{SERVER_URL}/refresh_face_profiles", timeout=2)
                except:
                    pass
                st.success(f"✅ **{name}** deleted.")
                st.session_state.pop("_del_target", None)
                st.rerun()
            except Exception as exc:
                st.error(f"Delete failed: {exc}")
    with dc2:
        if st.button("Cancel", use_container_width=True, key="btn_cancel_del"):
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Dialog: Register Person
# ─────────────────────────────────────────────────────────────────────────────
@st.dialog("Register Person", width="large")
def register_person_dialog():
    """
    Two-stage dialog:
      Stage 1 — registration form
      Stage 2 — back-search results + Done button
    State is held in st.session_state so it survives the auto-rerun that
    Streamlit performs after a form submission.
    """
    # ── Stage 2: back-search in progress or complete ─────────────────────────
    if st.session_state.get("_reg_stage") == "back_search":
        reg = st.session_state.get("_reg_info", {})
        st.success(f"✅ **{reg.get('name','')}** registered — Face ID **#{reg.get('face_id','?')}**")
        st.divider()
        st.subheader("🔎 Back-Searching Historical Records…")
        st.caption(
            "Scanning all past movement snapshots that were logged before this person "
            "was registered (unknown sightings) to retroactively attribute any matches."
        )

        if not st.session_state.get("_back_search_done"):
            _prog = st.progress(0, text="Starting scan…")
            _result = back_search_face_history(
                reg["name"], reg["face_id"], reg["embedding"],
                progress_bar=_prog
            )
            _prog.empty()
            st.session_state["_back_search_result"] = _result
            st.session_state["_back_search_done"]   = True

        # Show results
        _result = st.session_state.get("_back_search_result", {})
        if "error" in _result:
            st.error(f"Back-search error: {_result['error']}")
        elif _result.get("matched", 0) > 0:
            st.success(
                f"✅ Scanned **{_result['scanned']}** records — "
                f"retroactively linked **{_result['matched']}** historical "
                f"sighting(s) to **{reg.get('name','')}**!"
            )
        else:
            st.info(
                f"Scanned **{_result['scanned']}** records — "
                "no historical sightings found for this person."
            )

        if st.button("✅ Done", type="primary", use_container_width=True,
                     key="btn_reg_done"):
            # Clean up session state and close dialog
            for _k in ["_reg_stage", "_reg_info", "_back_search_done", "_back_search_result"]:
                st.session_state.pop(_k, None)
            st.rerun()
        return

    # ── Stage 1: registration form ────────────────────────────────────────────
    st.markdown("Upload a clear photo of the person's face to add them to the recognition database.")

    with st.form("register_person_form"):
        name          = st.text_input("Full Name").upper()
        uploaded_file = st.file_uploader("Upload Face Image", type=["jpg", "jpeg", "png"])
        run_backsearch = st.checkbox(
            "🔎 Back-search historical records after registration",
            value=True,
            help="After registering, scan all unattributed past movement snapshots "
                 "to find previous sightings of this person."
        )

        if st.form_submit_button("Extract Face & Register", type="primary",
                                  use_container_width=True):
            if name and uploaded_file:
                file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
                img        = cv2.imdecode(file_bytes, 1)

                try:
                    detector   = cv2.FaceDetectorYN.create(
                        os.path.join(MODELS_DIR, "face_detection_yunet.onnx"), "", (320, 320)
                    )
                    recognizer = cv2.FaceRecognizerSF.create(
                        os.path.join(MODELS_DIR, "face_recognition_sface.onnx"), ""
                    )

                    h, w = img.shape[:2]
                    detector.setInputSize((w, h))
                    _, faces = detector.detect(img)

                    if faces is not None and len(faces) > 0:
                        face         = faces[0]
                        face_align   = recognizer.alignCrop(img, face)
                        face_feature = recognizer.feature(face_align)
                        blob         = face_feature.tobytes()
                        now_str      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        with sqlite3.connect(DB_NAME) as conn:
                            conn.execute('''
                                INSERT INTO face_profiles (name, embedding, first_seen, last_seen)
                                VALUES (?, ?, ?, ?)
                                ON CONFLICT(name) DO UPDATE SET embedding=excluded.embedding
                            ''', (name, blob, now_str, now_str))
                            conn.execute(
                                "UPDATE face_profiles SET face_id = rowid "
                                "WHERE name = ? AND face_id IS NULL",
                                (name,)
                            )
                            _row = conn.execute(
                                "SELECT face_id FROM face_profiles WHERE name = ?",
                                (name,)
                            ).fetchone()
                            assigned_face_id = _row[0] if _row else None

                        # Notify vision server to reload profiles
                        try:
                            requests.post(f"{SERVER_URL}/refresh_face_profiles", timeout=2)
                        except:
                            pass

                        if run_backsearch and assigned_face_id is not None:
                            # Transition to Stage 2 (back-search)
                            st.session_state["_reg_stage"] = "back_search"
                            st.session_state["_reg_info"]  = {
                                "name":    name,
                                "face_id": assigned_face_id,
                                "embedding": blob
                            }
                            st.session_state.pop("_back_search_done", None)
                            st.session_state.pop("_back_search_result", None)
                            st.rerun()
                        else:
                            st.success(f"✅ Successfully registered **{name}**!")
                            if assigned_face_id is not None:
                                st.info(f"🪪 Assigned **Face ID: #{assigned_face_id}**")
                            st.rerun()
                    else:
                        st.error("No face detected in the image. Please try another one.")
                except Exception as exc:
                    st.error(f"Error processing face: {exc}")
            else:
                st.warning("Please provide a name and an image.")

# ─────────────────────────────────────────────────────────────────────────────
# Fragment: Live Monitor
# ─────────────────────────────────────────────────────────────────────────────
@st.fragment(run_every=2.0)
def live_monitor_fragment():
    col_log, col_vid = st.columns([1, 2.5])
    with col_vid:
        st.image(f"{SERVER_URL}/video_face", use_container_width=True, caption="Live Face Detection Stream")
    with col_log:
        ui_utils.icon_subheader("Recent Faces", "clock")
        with sqlite3.connect(DB_NAME) as conn:
            try:
                logs = pd.read_sql_query(
                    "SELECT face_id, event, name, timestamp "
                    "FROM face_movements ORDER BY id DESC LIMIT 10",
                    conn
                )
                if not logs.empty:
                    logs['name'] = logs['name'].apply(decrypt_data)
                    logs['face_id'] = logs['face_id'].apply(
                        lambda x: f"#{int(x)}" if x and int(x) != 0 else "—"
                    )
                    st.dataframe(
                        logs.rename(columns={"face_id": "ID", "event": "Event",
                                             "name": "Name", "timestamp": "Time"}),
                        hide_index=True,
                        use_container_width=True
                    )
                else:
                    st.info("No movements yet.")
            except:
                st.info("Database not initialized.")

# ─────────────────────────────────────────────────────────────────────────────
# Fragment: Alert Listener
# ─────────────────────────────────────────────────────────────────────────────
@st.fragment(run_every=1.0)
def alert_listener():
    try:
        response = requests.get(f"{SERVER_URL}/face_alerts", timeout=0.5)
        if response.status_code == 200:
            alerts = response.json().get("alerts", [])
            for alert in alerts:
                st.toast(f"ALERT: {alert['name']} detected at {alert['event']}!", icon="🚩")
    except: pass

# ─────────────────────────────────────────────────────────────────────────────
# Fragment: Face Roster (inline gallery after Register button)
# ─────────────────────────────────────────────────────────────────────────────
@st.fragment(run_every=10.0)
def face_roster_fragment():
    """
    Compact inline gallery displayed directly below the Register button.
    Shows every registered face with their photo, name, Face ID and watchlist status.
    Allows toggling watchlist on/off per person.
    """
    with sqlite3.connect(DB_NAME) as conn:
        profiles = pd.read_sql_query(
            "SELECT face_id, name, last_snapshot_path FROM face_profiles ORDER BY name",
            conn
        )
        watchlist_names = set(
            pd.read_sql_query("SELECT name FROM face_watchlist", conn)['name'].tolist()
        )

    if profiles.empty:
        return

    # Coerce face_id safely
    profiles['face_id'] = profiles['face_id'].apply(
        lambda x: int(x) if x is not None and str(x) != 'nan' else None
    )

    COLS = 4  # cards per row
    rows = [profiles.iloc[i:i+COLS] for i in range(0, len(profiles), COLS)]

    for row_df in rows:
        cols = st.columns(COLS)
        for col, (_, person) in zip(cols, row_df.iterrows()):
            with col:
                name        = person['name']
                fid         = person['face_id']
                snap_path   = person['last_snapshot_path']
                on_watchlist = name in watchlist_names
                fid_label   = f"ID #{fid}" if fid else ""

                # Photo
                img = get_decrypted_image(snap_path) if snap_path else None
                if img:
                    st.image(img, use_container_width=True)
                else:
                    # Placeholder when no snapshot yet
                    st.markdown(
                        """
                        <div style="background:#1e2530;border-radius:8px;
                                    height:90px;display:flex;align-items:center;
                                    justify-content:center;color:#555;font-size:28px;">
                        👤</div>
                        """,
                        unsafe_allow_html=True
                    )

                # Name + Face ID
                st.caption(f"**{name}**  {fid_label}")

                # Watchlist toggle
                wl_key = f"wl_{name}_{fid}"
                if on_watchlist:
                    if st.button("🚩 On Watchlist", key=wl_key,
                                 use_container_width=True, type="primary",
                                 help="Click to remove from watchlist"):
                        with sqlite3.connect(DB_NAME) as conn:
                            conn.execute(
                                "DELETE FROM face_watchlist WHERE name=?", (name,)
                            )
                        try:
                            requests.post(
                                f"{SERVER_URL}/refresh_face_profiles", timeout=2
                            )
                        except:
                            pass
                        st.rerun()
                else:
                    if st.button("➕ Watchlist", key=wl_key,
                                 use_container_width=True,
                                 help="Add to watchlist to trigger alerts"):
                        with sqlite3.connect(DB_NAME) as conn:
                            conn.execute(
                                "INSERT OR REPLACE INTO face_watchlist "
                                "(name, reason, added_on) VALUES (?, ?, ?)",
                                (name, "Flagged via dashboard",
                                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                            )
                        try:
                            requests.post(
                                f"{SERVER_URL}/refresh_face_profiles", timeout=2
                            )
                        except:
                            pass
                        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────
def face_ui():
    init_face_db()
    alert_listener()
    ui_utils.icon_header("Face Recognition & Access", "users")

    if st.button("Register New Person", type="primary", use_container_width=True):
        register_person_dialog()

    # Inline face roster: photo cards with watchlist control
    face_roster_fragment()

    st.divider()
    live_monitor_fragment()
    st.divider()

    with st.expander("👤 Face Intelligence", expanded=True):
        face_intel_fragment()
