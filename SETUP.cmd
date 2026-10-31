@echo off
setlocal DisableDelayedExpansion
if not exist "%~dp0.setup-payload\python\python.exe" goto missing
"%~dp0.setup-payload\python\python.exe" -I -X utf8 -B "%~dp0setup_project.py" --bundled-offline --offline --artifact-dir "%~dp0.setup-payload\wheels"
set "setup_status=%errorlevel%"
if "%setup_status%"=="0" goto finish
echo Setup did not finish. Keep your student files and saved runs.
if "%setup_status%"=="2" goto finish
echo If Windows blocks the supplied interpreter, ask your institution's IT team to approve it.
echo Keep the security policy in place. See SETUP.md.
goto finish
:missing
echo The supplied Adventure interpreter is missing. Extract the complete original ZIP to a writable folder.
echo Keep your student files and saved runs when replacing damaged setup files.
set "setup_status=2"
:finish
if /I "%~1"=="/nopause" goto exit
pause
:exit
exit /b %setup_status%
