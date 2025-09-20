@echo off
chcp 65001 >nul

set /p model_name=<model.txt

start "" /b ollama run %model_name%

timeout /t 5 /nobreak >nul

echo Set WshShell = WScript.CreateObject("WScript.Shell") > sendkeys.vbs
echo WshShell.AppActivate "ollama run" >> sendkeys.vbs
echo WshShell.SendKeys "^Z" >> sendkeys.vbs
cscript //nologo sendkeys.vbs

call dbwam_env\Scripts\activate.bat

python bot.py

pause