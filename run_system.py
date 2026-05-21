import subprocess
import time
import sys
import os
import signal

def run_system():
    print("🚀 Starting Property Management System...")
    
    # 1. Start Vision Server (FastAPI)
    print("📹 Starting Vision Server (FastAPI on port 8000)...")
    vision_process = subprocess.Popen(
        [sys.executable, "vision_server.py"]
    )
    
    # 2. Wait a moment for the server to bind
    time.sleep(2)
    
    # 3. Start Main App (Streamlit)
    print("📊 Starting Main Dashboard (Streamlit on port 8501)...")
    streamlit_process = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "Main_app.py", "--server.port", "8501"]
    )
    
    print("\n✅ Both services are running!")
    print("💡 Press Ctrl+C to stop both services.")
    print("-" * 50)

    try:
        # Monitor the processes and print their output
        while True:
            # Check if processes are still alive
            if vision_process.poll() is not None:
                print("❌ Vision Server has stopped unexpectedly.")
                break
            if streamlit_process.poll() is not None:
                print("❌ Streamlit App has stopped unexpectedly.")
                break
            
            # (Optional) You could read and print lines from their stdout here
            # But usually it's better to keep it clean.
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Stopping system...")
    finally:
        # Graceful shutdown
        vision_process.terminate()
        streamlit_process.terminate()
        print("👋 Services stopped successfully.")

if __name__ == "__main__":
    run_system()
