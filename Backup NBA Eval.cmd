@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m personal.maintenance backup
echo.
pause
