@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0opencode_dashboard.py" (
 echo Missing opencode_dashboard.py. Extract the full ZIP first.
 pause
 exit /b 1
)
where pyw.exe >nul 2>nul
if not errorlevel 1 (
 start "" pyw.exe -3 "%~dp0opencode_dashboard.py" --open --quiet
 exit /b 0
)
where pythonw.exe >nul 2>nul
if not errorlevel 1 (
 start "" pythonw.exe "%~dp0opencode_dashboard.py" --open --quiet
 exit /b 0
)
where py.exe >nul 2>nul
if not errorlevel 1 (
 py.exe -3 "%~dp0opencode_dashboard.py" --open
 if errorlevel 1 pause
 exit /b
)
where python.exe >nul 2>nul
if not errorlevel 1 (
 python.exe "%~dp0opencode_dashboard.py" --open
 if errorlevel 1 pause
 exit /b
)
echo Python 3.10 or newer is required. Install Python and run this file again.
echo If nothing opened, run START_DEBUG.cmd for diagnostic output.
pause
exit /b 1
