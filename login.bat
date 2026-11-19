@echo off
title Douyin Analyzer - Login
cd /d %~dp0
if exist "%~dp0browsers" set "PLAYWRIGHT_BROWSERS_PATH=%~dp0browsers"

echo ============================================
echo   Douyin Login
echo   A Chrome window will open. Login with
echo   Douyin APP (scan QR code) or account.
echo   Login state is saved long-term.
echo ============================================
set "ACCOUNT="
set /p ACCOUNT=Account name (Enter = default): 
if exist "%~dp0venv\Scripts\python.exe" (
  if "%ACCOUNT%"=="" (
    "%~dp0venv\Scripts\python.exe" app\douyin_login.py
  ) else (
    "%~dp0venv\Scripts\python.exe" app\douyin_login.py --account "%ACCOUNT%"
  )
) else (
  if "%ACCOUNT%"=="" (
    python app\douyin_login.py
  ) else (
    python app\douyin_login.py --account "%ACCOUNT%"
  )
)
pause
