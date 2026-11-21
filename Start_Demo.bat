@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>&1 || (echo Install Python 3.10 or newer first. & pause & exit /b 1)
set "PYTHONPATH=%CD%\src"
python examples\demo.py
pause
