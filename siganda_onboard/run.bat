@echo off
:: Siganda Secondary School — Staff WiFi Onboarding
:: Double-click this file to start the server

cd /d "%~dp0"

:: Set your credentials here
set WA_TOKEN=your_meta_whatsapp_token
set WA_PHONE_ID=your_phone_number_id
set ADMIN_WA_NUMBER=263771234567

:: Create venv if missing
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate
pip install -q -r requirements.txt

echo.
echo ============================================
echo   Siganda Staff WiFi Form
echo   Open browser at: http://localhost:5002
echo ============================================
echo.

python app.py
pause
