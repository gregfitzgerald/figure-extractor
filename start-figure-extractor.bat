@echo off
REM Launch Figure Extractor over http://localhost so the File System Access API
REM (folder tree + persistent projects + batch render) works -- these do NOT work
REM from file://. The core PDF-loading flow still works if you just open the HTML.

cd /d "%~dp0"

echo Starting Figure Extractor on http://localhost:8001 ...
echo (A separate window runs the server -- close it to stop.)

REM Serve via WSL's Python (WSL2 forwards localhost to Windows).
start "figure-extractor server (close to stop)" wsl python3 -m http.server 8001

timeout /t 2 >nul
start chrome "http://localhost:8001/index.html"

echo.
echo   App: http://localhost:8001/index.html
echo.
echo Prefer Edge? Paste the URL above into Edge instead (both are Chromium).
pause
