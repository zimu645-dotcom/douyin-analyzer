@echo off
title Douyin Analyzer - Full Check
cd /d %~dp0

echo ============================================
echo   Douyin Analyzer - Full Environment Check
echo ============================================

echo.
echo [1/10] Python:
python --version 2>&1

echo.
echo [2/10] Virtual env:
if exist venv (echo   venv OK) else (echo   [ERROR] venv missing)

echo.
echo [3/10] Key dependencies:
venv\Scripts\python -c "import fastapi; print('  fastapi', fastapi.__version__)" 2>&1
venv\Scripts\python -c "import multipart; print('  python-multipart OK')" 2>&1
venv\Scripts\python -c "import faster_whisper; print('  faster-whisper OK')" 2>&1
venv\Scripts\python -c "import playwright; print('  playwright OK')" 2>&1

echo.
echo [4/10] yt-dlp command path:
venv\Scripts\python -c "import sys,os; sys.path.insert(0,'app'); import services; p=services._ytdlp_path(); print('  path:', p); print('  exists:', os.path.exists(p))" 2>&1

echo.
echo [5/10] Whisper model files:
if exist models\model.bin (echo   model.bin OK) else (echo   [ERROR] model.bin MISSING)
if exist models\config.json (echo   config.json OK) else (echo   [WARN] config.json missing)
if exist models\tokenizer.json (echo   tokenizer.json OK) else (echo   [WARN] tokenizer.json missing)
if exist models\vocabulary.json (echo   vocabulary.json OK) else (echo   [WARN] vocabulary.json missing)

echo.
echo [6/10] Douyin cookies:
if exist cookies.txt (echo   cookies.txt exists) else (echo   [WARN] missing - run login.bat)

echo.
echo [7/10] API / Feishu config:
if exist app_output\config.json (
    venv\Scripts\python -c "import json; c=json.load(open('app_output/config.json',encoding='utf-8')); r=c.get('rewrite',{}); print('  primary key:', 'SET' if (r.get('primary') or {}).get('key') else 'EMPTY'); print('  fallback key:', 'SET' if (r.get('fallback') or {}).get('key') else 'EMPTY'); print('  vision key:', 'SET' if (c.get('vision') or {}).get('key') else 'EMPTY'); f=c.get('feishu',{}); print('  feishu:', 'CONFIGURED' if f.get('app_id') and f.get('app_token') else 'INCOMPLETE')" 2>&1
) else (
    echo   [INFO] config.json not found - will be created after first service start
)

echo.
echo [8/10] Browser:
if exist browsers (echo   browsers folder OK) else (echo   [WARN] browsers folder missing - playwright browser not installed?)
if exist chrome_profile (echo   chrome_profile OK) else (echo   [INFO] chrome_profile missing - will be created by login.bat)

echo.
echo [9/10] Test download a video (takes 10-30s)...
venv\Scripts\python -c "import sys,os,io; sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace'); sys.path.insert(0,'app'); import services; ok,t,d=services.download_audio('7628203393576572649','test'); print('  DOWNLOAD:', 'OK' if ok else 'FAILED', '|', (t or '')[:15], '|', d)" 2>&1

echo.
echo [10/10] Service process:
tasklist | findstr /i "launcher" >nul 2>&1 && echo   service running - close start.bat window first if retrying || echo   service NOT running (OK)

echo.
echo ============================================
echo   DONE! Please send the full output above.
echo ============================================
pause
