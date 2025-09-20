@echo off
chcp 65001 >nul

setlocal enabledelayedexpansion

set "model_name="

for /f "usebackq delims=" %%i in ("model.txt") do (
    set "content=!content!%%i^&echo."
)

echo Using %model_name%.

start "" /b ollama run %model_name%

echo Set WshShell = WScript.CreateObject("WScript.Shell") > sendkeys.vbs
echo WshShell.AppActivate "ollama run" >> sendkeys.vbs
echo WshShell.SendKeys "^Z" >> sendkeys.vbs
cscript //nologo sendkeys.vbs

call dbwam_env\Scripts\activate.bat

python bot.py

pause