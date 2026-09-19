@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-wb-learning-client.ps1"
set "result=%ERRORLEVEL%"
echo.
if not "%result%"=="0" echo Installation failed. Review the message above.
pause
exit /b %result%
