@echo off
setlocal

echo ============================================
echo   Brute Panel - building BrutePanel.exe
echo ============================================
echo.

where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install it from: https://nodejs.org/
    pause
    exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Install it from: https://www.python.org/downloads/
    echo When installing, check "Add python.exe to PATH".
    pause
    exit /b 1
)

if not exist ".env" (
    echo [ERROR] .env file not found
    echo Copy .env.example to .env and fill it in with your Firebase details, then run this script again.
    pause
    exit /b 1
)

echo [1/4] Installing npm dependencies...
call npm install
if errorlevel 1 goto :error

echo.
echo [2/4] Building the web app (npm run build)...
call npm run build
if errorlevel 1 goto :error

echo.
echo [3/4] Installing Python dependencies (pyinstaller, pywebview)...
python -m pip install --upgrade pip >nul
python -m pip install pyinstaller pywebview
if errorlevel 1 goto :error

echo.
echo [4/4] Building BrutePanel.exe...
python -m PyInstaller --noconfirm --onefile --windowed --name BrutePanel --add-data "build;build" desktop_launcher.py
if errorlevel 1 goto :error

echo.
echo ============================================
echo   Done! File: panel\dist\BrutePanel.exe
echo   Run it on the local machine.
echo ============================================
pause
exit /b 0

:error
echo.
echo [ERROR] Build failed. See the message above.
pause
exit /b 1
