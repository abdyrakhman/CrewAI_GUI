@echo off
rem Double-click or run: install.bat [parameters of install.ps1]
setlocal
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
if errorlevel 1 pause
endlocal
