@echo off
cd /d %~dp0app
set "PLAYWRIGHT_BROWSERS_PATH=%~dp0browsers"
echo ============================================
echo   Douyin Analyzer Service
echo   URL : http://127.0.0.1:8321
echo --------------------------------------------
echo   Open the URL in browser after startup.
echo   Service auto-stops ~20s after closing page.
echo   Close this window to stop it manually.
echo ============================================
..\venv\Scripts\python launcher.py
pause
