@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if "%~1"=="" (
  python "%~dp0theme_engine.py" list
  exit /b 0
)
if /i "%~1"=="reset" (
  python "%~dp0theme_engine.py" reset
  exit /b %errorlevel%
)
python "%~dp0theme_engine.py" apply "%~1"
