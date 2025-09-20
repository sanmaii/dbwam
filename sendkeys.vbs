Set WshShell = WScript.CreateObject("WScript.Shell") 
WshShell.AppActivate "ollama run" 
WshShell.SendKeys "^Z" 
