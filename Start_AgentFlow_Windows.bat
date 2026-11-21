@echo off
setlocal
cd /d "%~dp0"
py -3 -m venv .venv || (echo Python 3.10+ required & pause & exit /b 1)
call .venv\Scripts\activate.bat
python -m pip install -e ".[server]" || (echo Dependency installation failed & pause & exit /b 1)
python tools\start_local.py --browser
if errorlevel 1 pause
