@echo off
rem WC4 Engine Editor launcher: creates .venv on first run, then opens the editor window.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv || goto :err
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :err
)
".venv\Scripts\python.exe" app.py %*
goto :eof
:err
echo Setup failed. Install Python 3.10+ and try again.
pause
