@echo off
setlocal
cd /d "%~dp0"
where py.exe >nul 2>nul
if not errorlevel 1 (
 py.exe -3 "%~dp0opencode_dashboard.py" --open
) else (
 python.exe "%~dp0opencode_dashboard.py" --open
)
pause
