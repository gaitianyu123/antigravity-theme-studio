@echo off
cd /d "%~dp0"
where pythonw >nul 2>&1
if %errorlevel%==0 (
  start "" pythonw "%~dp0theme_engine.py" launch
) else (
  start "" /b python "%~dp0theme_engine.py" launch
)
exit /b 0
