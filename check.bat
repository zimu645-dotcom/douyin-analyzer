@echo off
title Douyin Analyzer - Environment Check
cd /d %~dp0

echo ============================================
echo   Douyin Analyzer - Environment Check
echo ============================================

echo.
echo [1/6] Python version:
python --version 2>&1

echo.
echo [2/6] Virtual env:
if exist venv (
    echo   venv OK
) else (
    echo   [ERROR] venv folder missing!
)

echo.
echo [3/6] Key dependencies:
venv\Scripts\python -c "import fastapi; print('  fastapi OK', fastapi.__version__)" 2>&1
venv\Scripts\python -c "import multipart; print('  python-multipart OK')" 2>&1
venv\Scripts\python -c "import faster_whisper; print('  faster-whisper OK')" 2>&1
venv\Scripts\python -c "import playwright; print('  playwright OK')" 2>&1
echo   yt-dlp command check:
venv\Scripts\yt-dlp.exe --version 2>&1
if errorlevel 1 (
    echo   [ERROR] yt-dlp not found in venv! Try system:
    where yt-dlp 2>&1
    if errorlevel 1 echo   [ERROR] yt-dlp NOT installed at all - run: pip install yt-dlp
)

echo.
echo [4/6] Whisper model file:
if exist models\model.bin (
    for %%A in (models\model.bin) do echo   model.bin exists (%%~zA bytes)
) else (
    echo   [ERROR] models\model.bin NOT found!
    echo   The model download failed during install.bat.
)

echo.
echo [5/6] Douyin cookies:
if exist cookies.txt (
    echo   cookies.txt exists
) else (
    echo   [WARN] cookies.txt NOT found - please run login.bat to login Douyin!
)

echo.
echo [6/6] Test download a video (takes 10-30s)...
venv\Scripts\python -c "import sys,os; sys.path.insert(0,'app'); import services; ok,t,d=services.download_audio('7628203393576572649','test'); print('  DOWNLOAD RESULT:', 'OK' if ok else 'FAILED', '| title:', t, '| duration:', d)" 2>&1

echo.
echo ============================================
echo   DONE! Please send the full output above.
echo ============================================
pause
