@echo off
setlocal
cd /d "%~dp0"
python -c "import os; assert os.name=='nt', 'Native Windows required'" || exit /b 1
python -m pip install -e ".[test,server]" || exit /b 1
python -m pytest -v tests/test_v050.py -k windows_job_cleans_child || exit /b 1
python -m pytest -q
exit /b %errorlevel%
