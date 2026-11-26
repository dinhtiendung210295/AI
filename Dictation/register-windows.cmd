@echo off
setlocal
cd /d "%~dp0"
echo Enter the extension ID shown at chrome://extensions.
set /p "EXTENSION_ID=Extension ID: "
".venv\Scripts\python.exe" register_native.py --extension-id "%EXTENSION_ID%"
echo.
pause
