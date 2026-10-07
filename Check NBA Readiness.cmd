@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m personal.maintenance check --online --players 4433134,3945274,3975,3112335
echo.
pause
