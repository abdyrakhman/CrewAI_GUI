@echo off
rem CrewAI Studio launcher. Kept ASCII-only: cmd interprets .bat bytes in the OEM code page,
rem so Cyrillic text here would break parsing. Russian messages live in the app itself.
setlocal
chcp 65001 >nul
title CrewAI Studio
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto run

echo.
echo  First launch: creating the virtual environment and installing CrewAI.
echo  This takes a few minutes and requires an internet connection.
echo.

set "PYLAUNCH="
where py >nul 2>nul
if not errorlevel 1 set "PYLAUNCH=py -3"
if not defined PYLAUNCH set "PYLAUNCH=python"

%PYLAUNCH% --version >nul 2>nul
if errorlevel 1 goto nopython

%PYLAUNCH% -m venv .venv
if errorlevel 1 goto venvfail

".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --upgrade pip
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto pipfail

:run
echo.
".venv\Scripts\python.exe" run.py %*
if errorlevel 1 pause
exit /b 0

:nopython
echo.
echo  [ERROR] Python 3.10-3.13 was not found.
echo          Install it from https://www.python.org/downloads/
echo          and tick "Add python.exe to PATH" during setup.
pause
exit /b 1

:venvfail
echo.
echo  [ERROR] Could not create the .venv environment.
pause
exit /b 1

:pipfail
echo.
echo  [ERROR] Installing dependencies failed.
echo          Check the internet connection and run start.bat again.
pause
exit /b 1
