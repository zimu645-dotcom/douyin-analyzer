@echo off
title Douyin Analyzer - Install
cd /d %~dp0
set "SRC=%CD%"

echo ============================================
echo   Douyin Video Analyzer - Install
echo ============================================
echo   Current location : %SRC%
echo.
echo   Step 1: Choose install drive  (C / D / E ...)
echo   Type a drive letter, case-insensitive:
set /p DRIVE=
if "%DRIVE%"=="" set "DRIVE=C"
set "DRIVE=%DRIVE:~0,1%"

REM ==== Build target path ====
if /i "%DRIVE%"=="%SRC:~0,1%" (
    set "TARGET=%SRC%"
) else (
    set "TARGET=%DRIVE%:\douyin-analyzer"
)
echo   Install location : %TARGET%
echo.
echo   Step 2: Press Enter to start (or type X to cancel)
set /p OK=
if /i "%OK%"=="x" exit

REM ==== If user chose another drive, create folder and copy project ====
if /i not "%TARGET%"=="%SRC%" (
    echo   Creating folder %TARGET% ...
    if not exist "%TARGET%" mkdir "%TARGET%"
    echo   Copying project files ...
    robocopy "%SRC%" "%TARGET%" /E /XD venv models browsers app_output output chrome_profile .git __pycache__ /XF cookies.txt *.pyc *.m4a *.mp4 *.mp3 >nul 2>&1
    cd /d "%TARGET%"
)

set "PLAYWRIGHT_BROWSERS_PATH=%CD%\browsers"
echo.
echo   Installing to : %CD%
echo   Everything installs into this folder.
echo.

REM ===== 1. Check / Auto-install Python =====
python --version >nul 2>&1
if errorlevel 1 (
    echo [1/5] Python not found, trying to auto-install Python 3.12...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements >nul 2>&1
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
    python --version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Auto-install failed. Please install Python 3.10+ manually:
        echo   Download: https://www.python.org/downloads/
        echo   IMPORTANT: Check "Add Python to PATH" during install.
        pause
        exit /b 1
    )
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

REM ===== 4. Install Chromium (into project folder) =====
echo [4/5] Installing Chromium browser (into project\browsers)...
python -m playwright install chromium

REM ===== 5. Download whisper model (medium, ~1.5GB) =====
echo [5/5] Downloading whisper model (medium, about 1.5GB)...
if not exist models\model.bin (
    echo  Downloading via HuggingFace mirror (faster in China)...
    set "HF_ENDPOINT=https://hf-mirror.com"
    python -c "from faster_whisper.utils import download_model; download_model('Systran/faster-whisper-medium', output_dir='models')"
    if errorlevel 1 (
        echo.
        echo [WARN] Auto download failed. Please download manually:
        echo   Visit  https://huggingface.co/Systran/faster-whisper-medium
        echo   Download model.bin / config.json / tokenizer.json / vocabulary.json
        echo   Put them into the "models" folder, then run install.bat again.
        pause
    )
) else (
    echo Model already exists, skip
)

REM ===== 6. Check / Install ffmpeg (needed for audio extraction) =====
echo [6/6] Checking ffmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo   ffmpeg not found, installing via winget...
    winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements >nul 2>&1
    ffmpeg -version >nul 2>&1
    if errorlevel 1 (
        echo   [WARN] ffmpeg install failed. Please install manually:
        echo   Download: https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
        echo   Add ffmpeg.exe/ffprobe.exe to system PATH.
    ) else (
        echo   ffmpeg installed OK (restart start.bat to use it)
    )
) else (
    echo   ffmpeg OK
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
