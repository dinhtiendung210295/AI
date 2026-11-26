@echo off
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Setup complete. Load extension in Chrome, then run register-windows.cmd.
pause
exit /b 0
:failed
echo Setup failed. Install Python 3.11+ and check the error above.
pause
exit /b 1
