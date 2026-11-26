@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" register_native.py --remove
echo.
pause
