@echo off
setlocal
title Kestrel Returns-Risk Service
cd /d "%~dp0"
set PORT=8000
if not "%~1"=="" set PORT=%~1

rem --- find Python 3 (py launcher first, then python) ---
set PY=
where py >nul 2>nul && (py -3 -c "import sys" >nul 2>nul && set PY=py -3)
if not defined PY (where python >nul 2>nul && (python -c "import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>nul && set PY=python))
if not defined PY (
  echo.
  echo  Python 3.9+ was not found.
  echo  Install it from https://www.python.org/downloads/  ^(tick "Add python.exe to PATH"^), then run this file again.
  echo.
  pause
  exit /b 1
)

echo Using: %PY%
echo Running self-tests...
%PY% -m unittest discover -s tests >"%TEMP%\kestrel_tests.log" 2>&1
if errorlevel 1 (
  echo  Self-tests FAILED - see %TEMP%\kestrel_tests.log
  pause
  exit /b 1
)
echo Self-tests passed.

echo Opening http://127.0.0.1:%PORT% in your browser...
start "" cmd /c "timeout /t 2 >nul & start http://127.0.0.1:%PORT%"
%PY% serve.py %PORT%
if errorlevel 1 (
  echo.
  echo  The service stopped. If port %PORT% is busy, run:  run.bat 8080
  pause
)
endlocal
