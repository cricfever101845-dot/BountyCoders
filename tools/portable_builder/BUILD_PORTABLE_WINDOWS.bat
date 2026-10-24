@echo off
setlocal
cd /d "%~dp0\..\.."
where py >nul 2>nul
if not errorlevel 1 (
    py -3 tools\portable_builder\build_portable.py --project "%CD%" --output "%CD%\dist" %*
) else (
    python tools\portable_builder\build_portable.py --project "%CD%" --output "%CD%\dist" %*
)
if errorlevel 1 pause
