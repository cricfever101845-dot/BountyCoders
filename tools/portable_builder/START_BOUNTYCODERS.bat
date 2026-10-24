@echo off
setlocal
cd /d "%~dp0"
if not exist "runtime\python\python.exe" (
  echo ERROR: The portable Python runtime is missing.
  echo Run the BUILD_PORTABLE_WINDOWS.bat file on the development PC first.
  pause
  exit /b 1
)
"runtime\python\python.exe" -B "launcher.py"
if errorlevel 1 pause
