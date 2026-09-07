@echo off
REM APIx setup - Windows.  Run from the repository root:  webapp\setup.bat
setlocal
cd /d "%~dp0.."

echo APIx setup
echo ----------------------------------------------------------------

where python >nul 2>&1
if errorlevel 1 (
  echo Python was not found on PATH.
  echo Install Python 3.10+ from python.org and tick "Add Python to PATH".
  exit /b 1
)
for /f "tokens=*" %%v in ('python --version') do echo   python      %%v

if not exist .venv (
  echo   venv        creating .venv
  python -m venv .venv
) else (
  echo   venv        .venv already exists
)
call .venv\Scripts\activate.bat

echo   packages    installing ^(a minute or two^)
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

echo   chromium    installing the browser Playwright drives
python -m playwright install chromium >nul

echo   database    applying schemas
python -c "from webapp.run import ensure_database; print('              ', ensure_database())"

echo ----------------------------------------------------------------
echo Done. Two commands from here:
echo.
echo   .venv\Scripts\activate
echo   python -m apix.cli useradd --generate-password
echo   python -m webapp.run
echo.
echo Then open http://localhost:8000
endlocal
