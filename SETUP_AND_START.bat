@echo off
setlocal enabledelayedexpansion

echo ======================================================
echo 🚀 PROPERTY MANAGEMENT SYSTEM - AUTOMATED SETUP
echo ======================================================
echo.

:: 1. Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python is not installed or not in PATH.
    echo Please install Python from https://www.python.org/
    pause
    exit /b
)

:: 2. Create Virtual Environment if it doesn't exist
if not exist "venv" (
    echo 📦 Creating Virtual Environment (this may take a minute)...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ❌ Failed to create virtual environment.
        pause
        exit /b
    )
)

:: 3. Activate Virtual Environment
echo 🔄 Activating Environment...
call venv\Scripts\activate

:: 4. Upgrade Pip
echo 🔼 Upgrading pip...
python -m pip install --upgrade pip >nul

:: 5. Install Dependencies
echo 📥 Installing required libraries...
echo (Note: This will download several GBs for AI support on the first run)
echo.

:: Check for NVIDIA GPU to decide which PyTorch to install
nvidia-smi >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ NVIDIA GPU Detected! Installing CUDA-enabled PyTorch for maximum speed...
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
) else (
    echo ℹ️ No NVIDIA GPU detected. Installing CPU version of libraries...
    pip install torch torchvision torchaudio
)

:: Install rest of the requirements
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo ❌ Installation failed. Please check your internet connection.
    pause
    exit /b
)

echo.
echo ✅ Setup Complete! 
echo 🚀 Launching the system...
echo.

:: 6. Launch the System
python run_system.py

pause
