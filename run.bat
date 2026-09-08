@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% --version >nul 2>nul || (echo Python 3.12 not found. Install from https://www.python.org/downloads/windows/ and tick "Add python.exe to PATH". & pause & exit /b 1)
%PY% scripts\bootstrap.py %*
pause
