@echo off
cd /d "%~dp0"

if not exist venv (
    echo Creating virtualenv...
    python -m venv venv
    venv\Scripts\pip install -q -r requirements.txt
)

echo.
echo   ZivoPay Service Center  ^>  http://localhost:5001
echo.
venv\Scripts\python seed.py
venv\Scripts\python main.py
