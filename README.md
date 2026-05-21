# 🏨 Unified Hotel Management System 

A modular, high-security ERP system built with Streamlit and AI. This system integrates real-time ALPR (Automatic License Plate Recognition), Guest Logistics, Maintenance Tracking, Inventory, and Financial Oversight.

## 🚀 Quick Start
1. **Clone the project** into a new folder.
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Set up AI Credentials**:
   Create a `.streamlit/secrets.toml` file and add your Gemini API Key and Encryption Key:
   ```toml
   GEMINI_API_KEY = "your_google_gemini_key"
   ENCRYPTION_KEY = "your_32_byte_base64_fernet_key"
   ```
4. **Start the Vision Server**:
   ```bash
   python vision_server.py
   ```
5. **Launch the Dashboard**:
   ```bash
   streamlit run Main_app.py
   ```

## 📂 Project Structure
The app is built using a modular architecture for easy maintenance:

*   `Main_app.py`: The main entry point and role-based router.
*   `vision_server.py`: Background ALPR processing server (FastAPI).
*   `auth_manager.py`: Handles secure login, SHA-256 password hashing, and user creation.
*   `security_dashboard.py`: Real-time vision monitoring and analytics dashboard.
*   `MEETINGS.py`: Meeting scheduler with video calls and AI-summarized minutes.
*   `reminders_page.py`: Management of airport pickups and driver directory.
*   `maintenance.py`: Work order system for facility repairs and tracking.
*   `INVENTORY.py`: Housekeeping logs and stock level management.
*   `REPORTS.py`: Digital logbook for shift handovers and incident reporting.
*   `EXPENSE_LOGGER.py`: Fuel and operational cost tracking (Naira currency).
*   `db_security.py`: AES-128 byte-level encryption for sensitive data (Plates, Audio).

## 🔑 Access Levels & Roles
The system restricts visibility based on the user's role:

| Role | Access |
| :--- | :--- |
| **Admin** | Full access to all modules and user management. |
| **Security** | Security Dashboard, ALPR Analytics, Logbook. |
| **Accounts** | Inventory, ALPR Analytics, Expenses, Logbook. |
| **Housekeeping** | Inventory, Maintenance, Logbook. |
| **HR** | Expenses, Logbook. |
| **Staff** | Airport Reminders, Maintenance, Logbook. |

## 🛡️ Default Credentials
Upon first launch, the system creates a master admin account:
*   **Username:** `ADMINISTRATOR`
*   **Password:** `BWG_ADMIN`
*   *Note: Please change the password immediately via the sidebar after your first login.*

## ⚠️ Prerequisites for AI Tracking
To use the **Security Dashboard**, ensure the following files are in the root directory:
1. `yolov8n.pt` (Standard YOLOv8 weights)
2. `license_plate_detector.pt` (Trained plate detection model)
3. `license_plate_video.mp4` (Your source camera feed or test video)

## 📊 Database
The system uses a local SQLite database (`alpr_data.db`). It is automatically initialized on the first run.