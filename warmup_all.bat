@echo off
REM Warmup All Marketplaces
REM This script runs warmup for all configured marketplaces

echo ========================================
echo      WARMUP ALL MARKETPLACES
echo ========================================
echo.
echo Starting warmup process...
echo This will open browsers for each marketplace.
echo You may need to solve CAPTCHAs manually.
echo.
echo Press Ctrl+C to cancel...
timeout /t 3 /nobreak >nul
echo.

REM Run the Python warmup script
python warmup_all.py

echo.
echo ========================================
echo      WARMUP COMPLETE
echo ========================================
echo.
pause
