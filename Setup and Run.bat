@echo off
title BitRot Guard v3 - Setup
cd /d "%~dp0"

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to your system PATH.
    echo Please install Python 3.10+ and check "Add Python to PATH" during setup.
    echo.
    pause
    exit /b
)

python setup_and_run.py
if %errorlevel% neq 0 (
    pause
)
