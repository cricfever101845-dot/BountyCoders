@echo off
setlocal
cd /d "%~dp0"
if not exist "app.py" (
    echo ERROR: Put this file inside your BountyCoders project folder beside app.py.
    pause
    exit /b 1
)
if not exist "bounty_runner.py" (
    echo ERROR: Run the BountyCoders Question Engine Upgrade installer first.
    pause
    exit /b 1
)
set "BC_RUNNER_MODE=portable"
echo.
echo BountyCoders - trusted LOCAL demo, no Docker.
echo Submitted code runs on this PC without isolation. Do not expose on LAN/internet.
echo Open http://127.0.0.1:5000 when the server starts.
echo Press Ctrl+C to stop.
echo.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" app.py
) else if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" app.py
) else (
    if exist "dist\BountyCoders_Submission_Windows_x64\runtime\python\python.exe" (
        "dist\BountyCoders_Submission_Windows_x64\runtime\python\python.exe" app.py
    ) else (
        py app.py
    )
)
if errorlevel 1 (
    echo.
    echo The server stopped with an error. Check the messages above.
    pause
)
