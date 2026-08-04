@echo off
REM ─── Giltgrave — one-click setup + play ─────────────────────────────────
REM First run: creates a Python env and installs dependencies (needs
REM Python 3.11+ from python.org, "Add to PATH" checked). After that it
REM just starts the game. The game opens in your browser at localhost:8000.
REM Multiplayer (accounts/PvP) connects automatically to the world server.
cd /d "%~dp0backend"

where py >nul 2>nul
if errorlevel 1 (
    echo Python not found — install Python 3.11+ from python.org first.
    pause
    exit /b 1
)

if not exist venv (
    echo First-time setup: installing dependencies ^(a few minutes^)...
    py -3 -m venv venv
    venv\Scripts\python -m pip install --quiet --upgrade pip
    venv\Scripts\python -m pip install --quiet -r requirements.txt
)

start "" http://localhost:8000
venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8000
