@echo off
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Run SETUP.cmd once to prepare this project's environment.
  pause
  exit /b 2
)
"%~dp0.venv\Scripts\python.exe" -X utf8 -B "%~dp0main.py"
set "AdventureStartExit=%ERRORLEVEL%"
if not "%AdventureStartExit%"=="0" pause
exit /b %AdventureStartExit%
