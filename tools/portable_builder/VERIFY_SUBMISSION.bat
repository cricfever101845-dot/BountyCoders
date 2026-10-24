@echo off
setlocal
cd /d "%~dp0"
if not exist "runtime\python\python.exe" (
  echo This is NOT a built portable release. Run BUILD_PORTABLE_WINDOWS.bat on your development PC first.
  pause
  exit /b 1
)
"runtime\python\python.exe" -B "verify_release.py"
if errorlevel 1 (
  echo FAILED. Do not submit this release until the errors are fixed.
) else (
  echo Verified. Ready to demonstrate.
)
pause
