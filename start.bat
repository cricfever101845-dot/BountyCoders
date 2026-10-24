@echo off
title Bounty Coders
cd /d "%~dp0"

echo ====================================
echo   Starting Bounty Coders Project
echo ====================================

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python and try again.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt

echo Starting server...
echo Access the site at: http://127.0.0.1:5000
python app.py
pause
