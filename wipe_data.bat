@echo off
echo 🧹 Voice Assistant Database Wipe Script
echo =========================================
echo WARNING: This will DELETE ALL DATA!
echo.
set /p confirm="Type 'WIPE' to confirm: "
if not "%confirm%"=="WIPE" (
    echo Operation cancelled.
    pause
    exit /b
)

echo.
echo Starting data wipe...
python wipe_data.py
echo.
pause
