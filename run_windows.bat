@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Meteora Pool Scanner and Filter V3.1  (Windows)
echo ============================================================

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating virtual environment .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo ERROR: failed to create the virtual environment.
        echo Please install Python 3.10+ and make sure "python" is in PATH.
        echo.
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

echo [2/3] Checking dependencies ...
python -c "import streamlit, requests, pandas, dotenv" 1>nul 2>nul
if errorlevel 1 (
    echo Installing dependencies, this may take a few minutes ...
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
)

if not exist ".env" (
    echo NOTE: .env not found - Feishu alerts are disabled.
)

echo [3/3] Starting Streamlit ... your browser will open http://localhost:8501
echo (Keep this window open. Press Ctrl+C to stop.)
python -m streamlit run app.py

echo.
echo App stopped.
pause