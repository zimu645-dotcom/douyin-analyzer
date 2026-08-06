@echo off
title Douyin Analyzer - One-Click Install
cd /d %~dp0

echo ============================================
echo   Douyin Video Analyzer - Auto Install
echo   It will setup everything automatically.
echo ============================================

REM ===== 1. Check Python =====
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found!
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo IMPORTANT: Check "Add Python to PATH" during install.
    pause
    exit /b 1
)
echo [1/5] Python OK

REM ===== 2. Create virtual environment =====
if not exist venv (
    echo [2/5] Creating virtual environment...
    python -m venv venv
) else (
    echo [2/5] venv already exists
)
call venv\Scripts\activate.bat

REM ===== 3. Install dependencies =====
echo [3/5] Installing dependencies (may take a few minutes)...
pip install -r requirements.txt

REM ===== 4. Install Chromium =====
echo [4/5] Installing Chromium browser...
python -m playwright install chromium

REM ===== 5. Download whisper model =====
echo [5/5] Downloading whisper model (about 460MB)...
if not exist models\model.bin (
    python -c "from faster_whisper.utils import download_model; download_model('Systran/faster-whisper-small', output_dir='models')"
) else (
    echo Model already exists, skip
)

echo.
echo ============================================
echo   INSTALL COMPLETE!
echo   Next steps:
echo     1. Double-click  login.bat   to login Douyin
echo     2. Double-click  start.bat   to start service
echo     3. Open http://127.0.0.1:8321 in browser
echo ============================================
pause
