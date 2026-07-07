@echo off
setlocal

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "VENV_PYTHON=%ROOT%.venv\Scripts\python.exe"

if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" "%ROOT%main.py"
) else (
    py -3 "%ROOT%main.py"
    if errorlevel 9009 (
        python "%ROOT%main.py"
    )
)

if errorlevel 1 (
    echo.
    echo Failed to start the game. Please check Python and dependencies.
    echo If this is the first run, install dependencies with:
    echo     python -m pip install -r requirements.txt
    echo.
    pause
)
