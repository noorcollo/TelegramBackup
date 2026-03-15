@echo off
setlocal enabledelayedexpansion
title TelegramBackup v3 — Made by 3ala

REM ── Already set up? Launch directly ─────────────────────────────────────────
if exist "%~dp0_ready_v3.flag" goto :launch

echo.
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║       📡  TelegramBackup v3  —  Made by 3ala                ║
echo  ║       First-time setup — this takes about 45 seconds        ║
echo  ╚══════════════════════════════════════════════════════════════╝
echo.

REM ── Check Python ─────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [!] Python not found on this machine.
    echo.
    echo  Please install Python 3.9 or higher:
    echo    1. Go to  https://python.org/downloads/
    echo    2. Download Python 3.x for Windows
    echo    3. Run the installer
    echo    4. IMPORTANT: Check the box "Add Python to PATH"
    echo    5. Click Install Now
    echo    6. Run this file again after install
    echo.
    start https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  [OK] Python %PYVER% detected.

REM ── Install dependencies ─────────────────────────────────────────────────────
echo  [*]  Installing required packages...
echo       This only happens once.
echo.
python -m pip install --upgrade pip --quiet --disable-pip-version-check
python -m pip install -r requirements.txt --quiet --disable-pip-version-check

if errorlevel 1 (
    echo.
    echo  [ERROR] Package installation failed.
    echo  Try right-clicking this file and choosing "Run as Administrator".
    pause
    exit /b 1
)

echo  [OK] All packages installed successfully.
echo ready > "%~dp0_ready_v3.flag"

:launch
echo  [*]  Launching TelegramBackup...
cd /d "%~dp0"

REM Try pythonw first (no console window), fall back to python
start "" pythonw telegram_backup_v3.py 2>nul
if errorlevel 1 (
    python telegram_backup_v3.py
)
