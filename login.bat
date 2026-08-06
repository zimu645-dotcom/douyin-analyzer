@echo off
title Douyin Analyzer - Login
cd /d %~dp0

echo ============================================
echo   Douyin Login
echo   A Chrome window will open. Login with
echo   Douyin APP (scan QR code) or account.
echo   Cookies will be saved automatically.
echo   Close the Chrome window when done.
echo ============================================
call venv\Scripts\activate.bat
python app/douyin_login.py
pause
