@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
where pythonw >nul 2>&1
if %errorlevel%==0 (
  start "" pythonw "%~dp0theme_gui.py"
) else (
  python "%~dp0theme_gui.py"
)
