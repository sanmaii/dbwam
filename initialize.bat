@echo off
chcp 65001 >nul

if not exist ".env" (
    echo .env file not found.
    pause
    exit /b 1
)

if not exist "bot.py" (
    echo bot.py file not found.
    pause
    exit /b 1
)

:ask_token
set /p user_token="Enter your discord bot token: "
if "%user_token%"=="" (
    echo Token cannot be empty, enter again.
    goto ask_token
)

:ask_model
set /p user_model="Enter your local AI model name: "
if "%user_model%"=="" (
    echo Model name cannot be empty, enter again.
    goto ask_model
)
echo.
echo. Updating configs...

(
    for /f "usebackq delims=" %%i in (".env") do (
        set "line=%%i"
        setlocal enabledelayedexpansion
        if "!line:DISCORD_TOKEN=Enter your token=!" neq "!line!" (
            echo DISCORD_TOKEN=!user_token!
        ) else (
            echo.!line!
        )
        endlocal
    )
) > ".env.tmp"
move ".env.tmp" ".env"

set %user_model% > "model.txt.tmp"
move "model.txt.tmp" "model.txt"

echo.
echo Configs updated suscessfully.
echo.

if not exist dbwam_env (
    echo Creating venv...
    python -m venv dbwam_env
)

call dbwam_env\Scripts\activate

pip install -r requirements.txt

echo.
echo venv created successfully, you may close this window.

pause
exit