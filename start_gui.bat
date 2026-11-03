@echo off
rem ============================================================
rem  GhostRec OBS - desktop app launcher
rem  Runs the PyQt6 app (window picker, live status, tray).
rem
rem  The console window stays open for diagnostics; you can
rem  minimize it. Use start_recorder.bat for the classic CLI.
rem ============================================================
setlocal
title GhostRec OBS
chcp 65001 >nul
cd /d "%~dp0"

rem --- find python ------------------------------------------------------------
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
    echo [!] Python not found in PATH - install Python 3.10+ first.
    pause
    exit /b 1
)

set "PYTHONUTF8=1"

%PY% -c "import PyQt6, obsws_python, win32gui" >nul 2>nul
if errorlevel 1 (
    echo [i] Installing GhostRec dependencies...
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [!] Failed to install dependencies.
        pause
        exit /b 1
    )
)

if not exist config.json (
    echo [i] Creating default config.json...
    copy /y config.example.json config.json >nul
)

%PY% app.py
if errorlevel 1 (
    echo.
    echo [!] GhostRec exited with an error.
    pause
)
