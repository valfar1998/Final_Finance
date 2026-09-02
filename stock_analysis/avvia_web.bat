@echo off
setlocal
cd /d "%~dp0"
echo.
echo  Stock Analysis - Yahoo + HTML multi-fonte
echo.
where python >nul 2>&1 || (echo Python mancante & pause & exit /b 1)
python -m pip install -r requirements.txt -q
set PORT=5055
start "" "http://127.0.0.1:%PORT%"
python app.py
pause
