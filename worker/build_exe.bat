@echo off
setlocal

echo ============================================
echo   Brute Worker - building BruteWorker.exe
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Install it from: https://www.python.org/downloads/
    echo When installing, check "Add python.exe to PATH".
    pause
    exit /b 1
)

echo [1/3] Installing dependencies...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :error

echo.
echo [2/3] Building BruteWorker.exe...
python -m PyInstaller --noconfirm --onefile --console --name BruteWorker agent.py
if errorlevel 1 goto :error

echo.
echo [3/3] Done.
echo   File: worker\dist\BruteWorker.exe
echo   Copy it to the GPU machine and run it - on first run a
echo   config.json will be created next to it, which you'll need to fill in.
echo ============================================
pause
exit /b 0

:error
echo.
echo [ERROR] Build failed. See the message above.
pause
exit /b 1
